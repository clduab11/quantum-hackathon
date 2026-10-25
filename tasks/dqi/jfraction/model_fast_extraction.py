# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Block-shear implementation/count model for in-place J extraction.

Each shear has sources disjoint from targets; it can use evaluation rank
len(A)+len(B)-1 with two clean field words. The ordinary field model below
checks the block scheduling, using schoolbook arithmetic within shears.
"""
import argparse
from . import model_jfraction as jm
import json
import pathlib
import random
from collections import Counter
from functools import cache



@cache
def shear_pieces(n, d, constant_b0, m=None):
    """Product pieces grouped by index modulo d; return actual sparse terms."""
    m = (n+1)//2 if m is None else m
    pieces = []
    for residue in range(min(d, m)):
        terms = [(i, j, d*i+j)
                 for i in range(1, (n-1)//d+1)
                 for j in range(residue, m, d)
                 if m <= d*i+j < n and not (constant_b0 and j == 0)]
        if not terms:
            continue
        iset = sorted({i for i,j,k in terms})
        jset = sorted({j for i,j,k in terms})
        targets = sorted({k for i,j,k in terms})
        rank = len(iset)+len(jset)-1
        best_rank,best_kind = min((len(terms),'naive'),(rank,'forward'),
                                  (len(iset)+len(targets)-1,'transpose_right'),
                                  (len(jset)+len(targets)-1,'transpose_left'))
        pieces.append({'terms':terms, 'is':iset, 'js':jset,
                       'rank':best_rank, 'method':best_kind,
                       'evaluation_rank':rank,
                       'transposed_rank':min(len(iset),len(jset))+len(targets)-1})
    return pieces


@cache
def shear_cost(n,d,constant_b0,m):
    return sum(p['rank'] for p in shear_pieces(n,d,constant_b0,m))


@cache
def toeplitz_plan(n,d):
    if n <= d:
        return 0,0
    candidates = [(toeplitz_plan(m,d)[0]+toeplitz_plan(n-m,d)[0]
                   +shear_cost(n,d,False,m),m) for m in range(1,n)]
    return min(candidates)


@cache
def power_plan(n,d):
    if n <= d:
        return 0,0
    candidates = [(power_plan(m,d)[0]+toeplitz_plan(n-m,d)[0]
                   +shear_cost(n,d,True,m),m) for m in range((n+d-1)//d,n)]
    return min(candidates)


class Model:
    def __init__(self):
        self.cost = Counter()
        self.operations = []
        self.shears = []

    def shear(self, data, src, dst, n, d, constant_b0=False, m=None):
        m = (n+1)//2 if m is None else m
        assert len(dst) == n
        target = set(dst[m:])
        if constant_b0 and n > d+1:
            self.cost[f'whole_power_evaluations_d{d}'] += (d+1)*(m-2)+1
        # src[i] names the coefficient of the Frobenius operand.
        for piece in shear_pieces(n,d,constant_b0,m):
            sources = {src[i] for i in piece['is']} | {dst[j] for j in piece['js']}
            assert not target & sources
            self.shears.append({'frobenius_power':d,
                                'left_cells':[src[i] for i in piece['is']],
                                'right_cells':[dst[j] for j in piece['js']],
                                'target_cells':sorted({dst[k] for i,j,k in piece['terms']}),
                                'coefficient_targets':{
                                    h:dst[d*(piece['is'][0]+h)+piece['js'][0]]
                                    for h in range(len(piece['is'])+len(piece['js'])-1)
                                    if m <= d*(piece['is'][0]+h)+piece['js'][0] < n},
                                'terms':[(dst[k],src[i],dst[j]) for i,j,k in piece['terms']],
                                'rank':piece['rank'],
                                'method':piece['method'],
                                'evaluation_rank':piece['evaluation_rank']})
            self.cost['products'] += piece['rank']
            self.cost[f'{"power_self" if constant_b0 else "toeplitz"}_products_d{d}'] += piece['rank']
            self.cost['naive_products'] += len(piece['terms'])
            self.cost['pieces'] += 1
            self.cost['output_vector_nonzeros_upper'] += piece['rank']*len({k for i,j,k in piece['terms']})
            self.cost['input_form_terms_upper'] += piece['rank']*(len(piece['is'])+len(piece['js']))
            for i,j,k in piece['terms']:
                op = (dst[k],src[i],dst[j],d)
                self.operations.append(op)
                data[dst[k]] ^= jm.mul(jm.power(data[src[i]],d), data[dst[j]])
        if constant_b0:
            for i in range(1,(n-1)//d+1):
                k = d*i
                if m <= k < n:
                    self.operations.append((dst[k],src[i],None,d))
                    data[dst[k]] ^= jm.power(data[src[i]],d)
                    self.cost['linear_terms'] += 1

    def toeplitz(self,data,src,dst,d):
        n = len(dst)
        if n <= d:
            return
        _,m = toeplitz_plan(n,d)
        self.toeplitz(data,src,dst[m:],d)
        self.shear(data,src,dst,n,d,m=m)
        self.toeplitz(data,src,dst[:m],d)

    def power_map(self,data,dst,d):
        n = len(dst)
        if n <= d:
            return
        _,m = power_plan(n,d)
        self.toeplitz(data,dst,dst[m:],d)
        self.shear(data,dst,dst,n,d,constant_b0=True,m=m)
        self.power_map(data,dst[:m],d)

    def reciprocal(self,data):
        d, exponent = 2,1
        while exponent < len(data)-1:
            self.power_map(data,list(range(len(data))),d)
            exponent *= 1+d
            d *= d

    def undo(self,data):
        for k,i,j,d in reversed(self.operations):
            data[k] ^= jm.power(data[i],d) if j is None else jm.mul(jm.power(data[i],d),data[j])




