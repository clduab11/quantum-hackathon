# SPDX-License-Identifier: Apache-2.0
"""Exact paired-product plans for one J=4 lookup stage from sparse kernel relations.

Port of mrmeows v8 balanced_plan.py and streamed_plan.py (cost-first-shape-screen
source); provenance: notices/30-dfthcsos.txt. The two planners differ only in how
they choose kernel relations; both accept a plan only after bit-exact tensor
reconstruction. No factor changes and no certificate input: same seed, same plan.
"""
import itertools
import random

import numpy as np

from tasks.dfthcsos.kernel_basis import (append_row, packed, paired_basis, paired_exchange,
                                         quotient_selection, reduce_row, select_relations,
                                         tensor_column)
from tasks.dfthcsos.paired_algebra import BinaryBasis, nullspace, set_bits


def plan_balanced(tensor, *, group_size=4, nrelations=36, seed=0, trials=24, plane_mode='original'):
    """Relations from every ``group_size`` low block, greedily kept degree-balanced."""
    H,L,m = tensor.shape
    rows = [packed(row) for row in tensor.reshape(H,L*m)]
    rng = random.Random(seed)
    perm = list(range(L))
    rng.shuffle(perm)
    pool = []
    for vs in itertools.combinations(range(L),group_size):
        block = np.concatenate([tensor[:,v,:] for v in vs],axis=1)
        for rel in nullspace([packed(row) for row in block],group_size*m):
            pool.append(sum(((rel >> (j*m)) & ((1 << m)-1)) << (v*m) for j,v in enumerate(vs)))
    rng.shuffle(pool)
    relations = []
    selected_basis = {}
    degrees = [0]*L
    supported = [(r,[i for i in range(L) if (r >> (m*i)) & ((1 << m)-1)]) for r in pool]
    while supported and len(relations) < nrelations:
        # Make high-degree coordinates expensive; randomize equal-cost choices.
        scores = [sum((degrees[i]+1)**4-degrees[i]**4 for i in idx)+0.25*rng.random() for _,idx in supported]
        which = min(range(len(scores)),key=lambda i: scores[i])
        rel,idx = supported.pop(which)
        if append_row(rel,selected_basis):
            relations.append(rel)
            for i in idx:
                degrees[i] += 1
    if len(relations) < nrelations:
        return None,{'seed':seed,'pool_rank':len(relations),'pool_size':len(pool),
                     'target_rank':L*m-nrelations,'contains_target':False}
    return _paired_plan(tensor,rows,relations,perm,seed,trials,plane_mode)


def plan_tensor(tensor, *, group_size=4, nrelations=36, seed=0, trials=24, plane_mode='original'):
    """Random relations from cyclic windows of ``group_size`` low coordinates."""
    H,L,m = tensor.shape
    rows = [packed(row) for row in tensor.reshape(H,L*m)]
    rng = random.Random(seed)
    perm = list(range(L))
    rng.shuffle(perm)
    extras = set(rng.sample(range(L),nrelations%L))
    relations = []
    for first in range(L):
        vs = [perm[(first+i)%L] for i in range(group_size)]
        block = np.concatenate([tensor[:,v,:] for v in vs],axis=1)
        count = nrelations//L+(first in extras)
        selected,_ = select_relations([packed(row) for row in block],group_size*m,count,rng)
        relations.extend(sum(((rel >> (j*m)) & ((1 << m)-1)) << (v*m) for j,v in enumerate(vs))
                         for rel in selected)
    return _paired_plan(tensor,rows,relations,perm,seed,trials,plane_mode)


def _planes(L,perm,chunks,m,plane_mode):
    planes = [(1 << i,1 << j) for i in range(L) for j in range(i+1,L)]
    for step in [1,2,3]:
        planes.extend(((1 << perm[i]) | (1 << perm[(i+step)%L]),1 << k) for i in range(L) for k in range(L)
                      if k not in [perm[i],perm[(i+step)%L]])
    if plane_mode != 'original':
        directions = [1 << i for i in range(L)]
        directions += [(1 << i) | (1 << j) for i in range(L) for j in range(i+1,L)]
        planes += [(a,b) for i,a in enumerate(directions) for b in directions[i+1:]]
        if plane_mode == 'triples':
            triples = [(1 << i) | (1 << j) | (1 << k) for i in range(L) for j in range(i+1,L) for k in range(j+1,L)]
            planes += [(a,1 << j) for a in triples for j in range(L)]
        planes = sorted(set(tuple(sorted((a,b,a^b))[:2]) for a,b in planes if a != b))
    if plane_mode == 'all':
        eqmap = {}
        for ell in range(1,1 << L):
            eq = []
            for cs in chunks:
                value = 0
                for j in set_bits(ell):
                    value ^= cs[j]
                if value:
                    eq.append(value)
            if nullspace(eq,m):
                eqmap[ell] = eq
        directions = sorted(eqmap)
        planes = sorted(set(tuple(sorted((a,b,a^b))[:2]) for i,a in enumerate(directions) for b in directions[i+1:]))
    return planes


def _paired_plan(tensor,rows,relations,perm,seed,trials,plane_mode):
    """Rank-two templates annihilating ``relations``, a paired basis, then exact reconstruction."""
    H,L,m = tensor.shape
    rb = {}
    for r in relations:
        append_row(r,rb)
    assert all((row & r).bit_count()%2 == 0 for row in rows for r in relations)
    chunks = [[(r >> (j*m)) & ((1 << m)-1) for j in range(L)] for r in relations]
    templates = []
    for a,b in _planes(L,perm,chunks,m,plane_mode):
        eq = []
        for cs in chunks:
            for ell in (a,b):
                v = 0
                for j in set_bits(ell):
                    v ^= cs[j]
                if v:
                    eq.append(v)
        V = nullspace(eq,m)
        directions = set(V)
        if len(V) <= 6:
            for code in range(1,1 << len(V)):
                v = 0
                for j in set_bits(code):
                    v ^= V[j]
                directions.add(v)
        for v in sorted(directions):
            if v:
                templates.append((tensor_column(v,a,m),tensor_column(v,b,m),v,a,b))
    span = {}
    for a,b,*_ in templates:
        append_row(a,span)
        append_row(b,span)
    target = L*m-len(rb)
    report = {'plane_mode':plane_mode,'seed':seed,'H':H,'L':L,'O':m,'relations_rank':len(rb),
              'target_rank':target,'span_rank':len(span),
              'contains_target':all(not reduce_row(row,span) for row in rows),'template_count':len(templates)}
    if len(span) != target or not report['contains_target'] or target%2:
        return None,report
    selected,attempts = quotient_selection(templates,target,L,seed+701,trials=trials)
    if selected is None:
        selected,attempts = paired_basis(templates,target,seed+1901,trials)
    if selected is None:
        selected,attempts = paired_exchange(templates,target,seed+3717,trials=trials)
    report['basis_attempts'] = attempts
    if selected is None:
        return None,report
    basis = BinaryBasis()
    for i in selected:
        a,b,*_ = templates[i]
        assert basis.add(a) and basis.add(b)
    solutions = [basis.solve(row) for row in rows]
    assert all(s is not None for s in solutions)
    terms = []
    reconstructed = [0]*H
    for j,i in enumerate(selected):
        a,b,v,ell1,ell2 = templates[i]
        h1 = sum(((s >> (2*j)) & 1) << h for h,s in enumerate(solutions))
        h2 = sum(((s >> (2*j+1)) & 1) << h for h,s in enumerate(solutions))
        terms.append({'target_direction':v,'factors':[(h1,ell1),(h2,ell2)]})
        for h in set_bits(h1):
            reconstructed[h] ^= a
        for h in set_bits(h2):
            reconstructed[h] ^= b
    if reconstructed != rows:
        raise AssertionError('paired plan does not reconstruct the coefficient tensor')
    report['pairs'] = len(selected)
    report['exact_tensor_reconstruction'] = True
    return terms,report
