# SPDX-License-Identifier: Apache-2.0
"""Exact parent-live low-monomial cache schedules, no synthesis/native work.

Reordering paired XOR products is exact: all controls depend only on address,
and each target operation is XOR by an address function. Pure-low corrections
are consolidated in Plan.pure and performed only after every paired product.
For each tested order, dynamic programming finds the minimum computation count
over ALL canonical-parent-closed caches of the requested capacity. Order search
itself is only a few deterministic grouping heuristics, not global optimality.
"""
from functools import lru_cache
from dataclasses import dataclass
import numpy as np

LOW=[m for m in range(1,16)if m.bit_count()>=2]
INDEX={m:j for j,m in enumerate(LOW)}

def parent(m):return m^(1<<(m.bit_length()-1))

def closure(monomials):
    result=set()
    for original in monomials:
        m=int(original)
        if not 0<=m<16:raise ValueError('not a low4 monomial')
        while m.bit_count()>=2:
            result.add(m);m=parent(m)
    return sum(1<<INDEX[m]for m in result)

def members(mask):return [m for j,m in enumerate(LOW)if(mask>>j)&1]

def closed(mask):return closure(members(mask))==mask

def product_requirement(product):
    poly=int(product.left1)|int(product.left2)
    if poly&1:raise ValueError('constant controls not supported by existing emitter')
    monomials=[i for i in range(1,16)if(poly>>i)&1]
    return closure(monomials)

@lru_cache(None)
def states_and_cost(capacity):
    if not 1<=capacity<=11:raise ValueError('capacity must be1..11')
    states=[m for m in range(1<<11)if m.bit_count()<=capacity and closed(m)]
    cost=np.array([[(t&~s).bit_count()for t in states]for s in states],dtype=np.int16)
    return np.array(states,dtype=np.int16),cost

def requirements(plan):
    if plan.low_bits!=4 or plan.blocks is not None:raise ValueError('need an unblocked low4 plan')
    req=[product_requirement(p)for p in plan.products]
    for m in plan.pure:
        if not(m<16 or(m&15)==0):raise ValueError('Plan.pure contains a mixed monomial')
    return req

def events_for_order(plan,order):
    events=[]
    # Consecutive same-required products use one cache state.
    for index in order:
        r=product_requirement(plan.products[index])
        if events and events[-1]['kind']=='products'and events[-1]['required']==r:
            events[-1]['indices'].append(int(index))
        else:events.append(dict(kind='products',indices=[int(index)],required=r))
    # All pure-low terms are postponed. Descending order is canonical postorder;
    # DP can retain ancestors for the later pure corrections without recompute.
    for m in sorted((m for m,v in plan.pure.items()if m<16 and m.bit_count()>=2 and v),reverse=True):
        events.append(dict(kind='pure_low',monomial=int(m),required=closure([m])))
    return events

def optimize_cache(plan,order,capacity=8,label='fixed'):
    req=requirements(plan)
    if any(r.bit_count()>capacity for r in req):raise ValueError('one product requires more low products than capacity')
    order=list(map(int,order))
    if sorted(order)!=list(range(len(plan.products))):raise ValueError('order is not a product permutation')
    events=events_for_order(plan,order);states,cost=states_and_cost(capacity);M=len(states)
    INF=np.int32(1000000);dp=np.full(M,INF,dtype=np.int32);dp[0]=0;backs=[]
    for event in events:
        r=event['required'];dest=np.flatnonzero((states&r)==r)
        values=dp[:,None]+cost[:,dest];old=np.argmin(values,axis=0)
        new=np.full(M,INF,dtype=np.int32);new[dest]=values[old,np.arange(len(dest))]
        back=np.full(M,-1,dtype=np.int16);back[dest]=old;backs.append(back);dp=new
    end=int(np.argmin(dp));computations=int(dp[end]);chosen=[]
    for i in range(len(events)-1,-1,-1):
        chosen.append(int(states[end]));end=int(backs[i][end])
        if end<0:raise RuntimeError('cache DP backpointer is missing')
    chosen.reverse()
    if end!=0:raise RuntimeError('cache DP did not return to the empty cache')
    out=dict(label=label,capacity=capacity,product_order=order,events=[dict(e,cache=s)for e,s in zip(events,chosen)],
        low_computations=computations,min_live_required=max([r.bit_count()for r in req]+[0]),
        peak_live=max([s.bit_count()for s in chosen]+[0]),cache_states_considered=M,
        optimal_retention_for_this_fixed_order=True,globally_optimal_order_claim=False)
    audit(plan,out);return out

def _require(ok, message):
    """Explicit check. `assert` disappears under `python -O`; a cache audit must not."""
    if not ok:
        raise RuntimeError(message)

def audit(plan,schedule):
    """Exact lifetime/parent/control audit, independent of native emission."""
    current=set();computations=0;erases=0;done=[];pure=[];peak=0
    for e in schedule['events']:
        target=set(members(e['cache']))
        _require(closed(e['cache']) and len(target)<=schedule['capacity'],
                 f"cache {e['cache']} is not closed within capacity {schedule['capacity']}")
        for m in sorted(current-target,reverse=True):
            _require(parent(m).bit_count()<2 or parent(m)in current,
                     f'erasing {m} while parent {parent(m)} is not live')
            _require(not any(parent(child)==m for child in current if child!=m),
                     f'erasing {m} while a child is still live')
            current.remove(m);erases+=1
        for m in sorted(target-current):
            _require(parent(m).bit_count()<2 or parent(m)in current,
                     f'computing {m} while parent {parent(m)} is not live')
            current.add(m);computations+=1;peak=max(peak,len(current))
        _require(current==target, f'cache state {sorted(current)} != target {sorted(target)}')
        if e['kind']=='products':
            for i in e['indices']:
                need=set(members(product_requirement(plan.products[i])))
                _require(need<=current, f'product {i} controls {sorted(need-current)} are not cached')
                done.append(i)
        else:
            _require(e['monomial'] in current, f"pure monomial {e['monomial']} is not cached")
            pure.append(e['monomial'])
    for m in sorted(current,reverse=True):
        _require(parent(m).bit_count()<2 or parent(m)in current,
                 f'final erase of {m} while parent {parent(m)} is not live')
        current.remove(m);erases+=1
    _require(not current and sorted(done)==list(range(len(plan.products))),
             f'unfinished cache {sorted(current)} or products {sorted(done)}')
    expected=sorted(m for m,v in plan.pure.items()if v and m<16 and m.bit_count()>=2)
    _require(sorted(pure)==expected and computations==schedule['low_computations'] and erases==computations,
             f'pure {sorted(pure)} != {expected} or computations {computations}/{erases} '
             f"!= {schedule['low_computations']}")
    _require(peak<=schedule['capacity'], f"peak live {peak} exceeds capacity {schedule['capacity']}")
    return dict(parent_live_on_every_compute_and_erase=True,all_low_clean_at_end=True,
                computes=computations,erases=erases,peak_live=peak,pure_low_deferred=True)

def candidate_orders(plan,capacity=8):
    req=requirements(plan);groups={}
    for i,r in enumerate(req):groups.setdefault(r,[]).append(i)
    orders={'original':list(range(len(req))),
            'stable_groups':[i for r in groups for i in groups[r]],
            'lex_groups':[i for r in sorted(groups)for i in groups[r]]}
    remaining=set(groups);now=0;greedy=[]
    while remaining:
        r=min(remaining,key=lambda r:((r&~now).bit_count(),-len(groups[r]),r))
        greedy.extend(groups[r]);remaining.remove(r);now=r
    orders['nearest_required']=greedy
    states,_=states_and_cost(capacity)
    for ratio in(False,True):
        remaining=set(groups);now=0;order=[]
        while remaining:
            scored=[]
            for state in states:
                state=int(state);covered=[r for r in remaining if r&~state==0]
                count=sum(len(groups[r])for r in covered)
                if not count:continue
                new=(state&~now).bit_count()
                key=((count/(new+1))if ratio else count,-new,-state.bit_count(),-state)
                scored.append((key,state,covered))
            _,state,covered=max(scored,key=lambda x:x[0])
            for r in sorted(covered,key=lambda r:(-len(groups[r]),r)):
                order.extend(groups[r]);remaining.remove(r)
            now=state
        orders['coverage_ratio'if ratio else'coverage_count']=order
    return orders

def make_schedule(plan,capacity=8):
    results=[]
    for label,order in candidate_orders(plan,capacity).items():
        s=optimize_cache(plan,order,capacity,label);results.append(s)
    best=min(results,key=lambda s:(s['low_computations'],s['peak_live'],s['label']))
    return best,[dict(label=s['label'],low_computations=s['low_computations'],peak_live=s['peak_live'])for s in results]
