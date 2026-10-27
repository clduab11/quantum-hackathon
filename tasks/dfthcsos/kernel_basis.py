# SPDX-License-Identifier: Apache-2.0
"""Exact GF(2) row spaces and paired-basis selection for the J=4 planners.

Port of mrmeows v8 kernel_planes.py, hyper_kernel.py and pair_exchange.py
(cost-first-shape-screen source); provenance: notices/30-dfthcsos.txt.
Every selected basis is checked with exact GF(2) arithmetic, never sampling.
"""
import random

from tasks.dfthcsos.paired_algebra import BinaryBasis, nullspace, set_bits


def packed(row):
    return sum(int(value) << j for j,value in enumerate(row))


def tensor_column(direction,lowform,m):
    return sum(direction << (m*j) for j in set_bits(lowform))


def reduce_row(value,pivots):
    while value:
        p = value.bit_length()-1
        if p not in pivots:
            break
        value ^= pivots[p]
    return value


def append_row(value,pivots):
    value = reduce_row(value,pivots)
    if not value:
        return False
    pivots[value.bit_length()-1] = value
    return True


def select_relations(rows,width,dimension,rng):
    """``dimension`` independent random kernel vectors of the packed ``rows``."""
    kernel = nullspace(rows,width)
    if len(kernel) < dimension:
        raise ValueError('requested kernel dimension exceeds the actual nullity')
    chosen = []
    span = {}
    while len(chosen) < dimension:
        mask = rng.getrandbits(len(kernel))
        value = 0
        for j in set_bits(mask):
            value ^= kernel[j]
        if append_row(value,span):
            assert all((value & row).bit_count()%2 == 0 for row in rows)
            chosen.append(value)
    return chosen,len(kernel)


def paired_basis(templates,target_rank,seed,trials):
    """Greedy: add both columns of a template, or neither."""
    rng = random.Random(seed)
    reports = []
    for trial in range(trials):
        order = list(range(len(templates)))
        rng.shuffle(order)
        span = {}
        chosen = []
        for i in order:
            a,b,*_ = templates[i]
            ar = reduce_row(a,span)
            if not ar:
                continue
            p = ar.bit_length()-1
            span[p] = ar
            br = reduce_row(b,span)
            if not br:
                del span[p]
                continue
            span[br.bit_length()-1] = br
            chosen.append(i)
            if len(span) == target_rank:
                reports.append({'trial':trial,'rank':len(span)})
                return chosen,reports
        reports.append({'trial':trial,'rank':len(span)})
    return None,reports


def quotient_selection(templates,target,L,seed,trials=64):
    """Pick mixed templates spanning the quotient by single-low templates, then fill each low space."""
    W0 = {}
    coordinate = []
    spaces = [{} for _ in range(L)]
    for i,(a,b,v,ell1,ell2) in enumerate(templates):
        if ell1.bit_count() == ell2.bit_count() == 1:
            left,right = ell1.bit_length()-1,ell2.bit_length()-1
            coordinate.append((i,left,right,v))
            append_row(a,W0)
            append_row(b,W0)
            append_row(v,spaces[left])
            append_row(v,spaces[right])
    pivots = sorted(W0.items(),reverse=True)
    def quotient(v):
        for p,row in pivots:
            if v >> p & 1:
                v ^= row
        return v
    mixed = []
    for i,(a,b,v,ell1,ell2) in enumerate(templates):
        ar,br = quotient(a),quotient(b)
        if ar and not br and ell2.bit_count() == 1:
            mixed.append((i,ar,ell2.bit_length()-1,v))
        elif br and not ar and ell1.bit_count() == 1:
            mixed.append((i,br,ell1.bit_length()-1,v))
    qrank = target-len(W0)
    dims = [len(x) for x in spaces]
    rng = random.Random(seed)
    attempts = []
    for trial in range(trials):
        order = mixed.copy()
        rng.shuffle(order)
        qspan = {}
        local = [{} for _ in range(L)]
        chosen = []
        for i,q,vertex,v in order:
            qr = reduce_row(q,qspan)
            vr = reduce_row(v,local[vertex])
            if qr and vr:
                qspan[qr.bit_length()-1] = qr
                local[vertex][vr.bit_length()-1] = vr
                chosen.append(i)
        if len(qspan) != qrank:
            attempts.append({'trial':trial,'quotient_rank':len(qspan),'required':qrank})
            continue
        pool = coordinate.copy()
        rng.shuffle(pool)
        while 2*len(chosen) < target:
            deficit = [dims[j]-len(local[j]) for j in range(L)]
            best = None
            for i,left,right,v in pool:
                if not deficit[left] or not deficit[right]:
                    continue
                lr = reduce_row(v,local[left])
                rr = reduce_row(v,local[right])
                if not lr or not rr:
                    continue
                score = (deficit[left]+deficit[right],min(deficit[left],deficit[right]))
                if best is None or score > best[0]:
                    best = (score,i,left,right,lr,rr)
            if best is None:
                break
            _,i,left,right,lr,rr = best
            local[left][lr.bit_length()-1] = lr
            local[right][rr.bit_length()-1] = rr
            chosen.append(i)
        span = {}
        for i in chosen:
            append_row(templates[i][0],span)
            append_row(templates[i][1],span)
        attempts.append({'trial':trial,'quotient_rank':len(qspan),'rank':len(span),'pairs':len(chosen)})
        if 2*len(chosen) == len(span) == target:
            return chosen,{'W0':len(W0),'qrank':qrank,'attempts':attempts}
    return None,{'W0':len(W0),'qrank':qrank,'attempts':attempts}


def paired_exchange(templates,target,seed=0,trials=16):
    """Greedy pairs, then repeatedly swap one selected pair for two quotient-independent pairs."""
    rng = random.Random(seed)
    best = []
    trace = []
    for trial in range(trials):
        order = list(range(len(templates)))
        rng.shuffle(order)
        span = {}
        selected = []
        for i in order:
            a,b = templates[i][:2]
            ar = reduce_row(a,span)
            if not ar:
                continue
            pivot = ar.bit_length()-1
            span[pivot] = ar
            br = reduce_row(b,span)
            if not br:
                del span[pivot]
                continue
            span[br.bit_length()-1] = br
            selected.append(i)
            if len(span) == target:
                return selected,{'method':'exchange','trace':trace,'greedy_trial':trial}
        if len(selected) > len(best):
            best = selected
    selected = best
    for _ in range(target//2):
        rank = 2*len(selected)
        if rank == target:
            return selected,{'method':'exchange','trace':trace}
        basis = BinaryBasis()
        for i in selected:
            assert basis.add(templates[i][0]) and basis.add(templates[i][1])
        for a,b,*_ in templates:
            basis.add(a)
            basis.add(b)
            if len(basis.vectors) == target:
                break
        if len(basis.vectors) != target:
            raise ValueError('Incomplete template span')
        coords = [(basis.solve(t[0]),basis.solve(t[1])) for t in templates]
        remove_order = list(range(len(selected)))
        rng.shuffle(remove_order)
        found = None
        for removed in remove_order:
            shift = 2*removed
            planes = {}
            for j,(a,b) in enumerate(coords):
                ar = ((a >> shift) & 3) | ((a >> rank) << 2)
                br = ((b >> shift) & 3) | ((b >> rank) << 2)
                if not ar or not br or ar == br:
                    continue
                plane = tuple(sorted((ar,br,ar^br)))
                if plane in planes:
                    continue
                for other,k in planes.items():
                    if not any(v in other for v in plane):
                        found = (removed,j,k)
                        break
                if found:
                    break
                planes[plane] = j
            if found:
                break
        if not found:
            trace.append({'rank':rank,'augmentation':False})
            return None,{'method':'exchange','trace':trace}
        removed,j,k = found
        selected = [i for pos,i in enumerate(selected) if pos != removed]+[j,k]
        span = {}
        for i in selected:
            assert append_row(templates[i][0],span) and append_row(templates[i][1],span)
        assert len(span) == rank+2
        trace.append({'rank_before':rank,'rank_after':len(span),'removed_position':removed,'inserted':[j,k]})
    return None,{'method':'exchange','trace':trace}
