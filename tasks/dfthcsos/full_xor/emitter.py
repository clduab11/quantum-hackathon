# SPDX-License-Identifier: Apache-2.0
"""Staged arbitrary-target XOR emitter with clean dedicated scratch.

All del_and calls have their original AND parents live. Its documented HMR+
conditional-CZ cleanup returns the child to zero; the fixed slot can then be
reinitialized. Product parity maps are restored before any cache transition.
"""
import kickmix as km
from tasks.dfthcsos.full_xor.paired_anf import bits, Plan
from tasks.dfthcsos.full_xor.scheduler import audit, parent, members

def require(ok, message):
    """Explicit check. `assert` disappears under `python -O`; emission checks must not."""
    if not ok:
        raise RuntimeError(message)

def high_masks(addresses):
    return [h<<4 for h in range(1,((int(addresses)-1)>>4)+1)if h.bit_count()>=2]

def lifted_plan(plan,addresses=1220):
    """A defined polynomial-extension fixture, NOT a new factorization table."""
    if plan.blocks is not None or plan.low_bits!=4:raise ValueError('need unblocked low4 plan')
    if addresses<plan.addresses:raise ValueError('use exact prefix restriction before lifting')
    cache=[m for m in range(1,16)if m.bit_count()>=2]+high_masks(addresses)
    return Plan(int(addresses),plan.batch,plan.brot,4,list(plan.products),dict(plan.pure),list(plan.ranks),cache,parity_scratch=0)

def build_staged(plan,schedule,addresses=None):
    audit(plan,schedule)
    if plan.batch!=5 or plan.brot not in (7,8):raise ValueError('five 7/8-bit words required')
    brot=plan.brot
    if not 1<=schedule['capacity']<=11:raise ValueError('low cache capacity must be1..11')
    A=plan.addresses if addresses is None else int(addresses)
    if A!=plan.addresses:raise ValueError('lift the Plan explicitly before emission')
    high=[m for m in plan.cache_masks if m>=16]
    if (A-1).bit_length()+5*brot+len(high)+schedule['capacity']>128:raise ValueError('cache exceeds 128-qubit layout')
    from tasks.dfthcsos.full_xor.validation import independent_truth
    for value in independent_truth(plan):
        if any(((value>>(brot*j+brot-1))&1)!=((value>>(brot*j+brot-2))&1)for j in range(5)):
            raise ValueError('delta is not canonical sign encoded')
    if plan.low_bits!=4 or plan.blocks is not None or plan.parity_scratch!=0:
        raise ValueError('need in-place unblocked low4 plan')
    b=km.CircuitBuilder();selection=b.create_quantum_register((A-1).bit_length(),'selection')
    words=[b.create_quantum_register(plan.brot,f'word_{j}')for j in range(plan.batch)]
    targets=[q for word in words for q in word]
    keep=(1<<(5*brot))-1
    cache={0:True,**{1<<i:q for i,q in enumerate(selection)}}
    high_pool=b.alloc_qubits(len(high));low_extra=b.alloc_qubits(schedule['capacity']);low_pool=list(low_extra)
    for m,q in zip(high,high_pool):
        top=1<<(m.bit_length()-1)
        b.init_and(cache[m^top],cache[top],q);cache[m]=q
    low={};free=list(low_pool);computes=0;erases=0;peak=0;product_count=0;controls_checked=0
    word_ids={q.id for q in targets}
    def transition(target_mask):
        nonlocal computes,erases,peak
        wanted=set(members(target_mask))
        for m in sorted(set(low)-wanted,reverse=True):
            top=1<<(m.bit_length()-1);q=low.pop(m)
            require(m^top in cache and top in cache, f'erasing {m} without both parents cached')
            require(not any(parent(x)==m for x in low), f'erasing {m} while a child is still live')
            b.del_and(cache[m^top],cache[top],q);del cache[m];free.append(q);erases+=1
        for m in sorted(wanted-set(low)):
            top=1<<(m.bit_length()-1)
            require(m^top in cache and top in cache and free, f'computing {m} without parents and a free slot')
            q=free.pop();b.init_and(cache[m^top],cache[top],q);low[m]=q;cache[m]=q;computes+=1
            peak=max(peak,len(low))
    def pure_fanout(mask,fanout):
        for k in bits(fanout&keep):b.cx(cache[mask],targets[k])
    def product(p):
        nonlocal controls_checked,product_count
        require(not((int(p.right1)|int(p.right2))&1), 'constant product control unsupported')
        aa={cache[m].id for m in bits(p.left1)}
        aa.update(cache[h<<4].id for h in bits(p.right2))
        bb={cache[m].id for m in bits(p.left2)}
        bb.update(cache[h<<4].id for h in bits(p.right1))
        require(aa and bb and aa!=bb, 'product controls are empty or identical')
        require(not((aa|bb)&word_ids), 'nonborrowed output used as a control/workspace')
        pp=min(aa);use_a=pp in bb;bprime=bb^aa if use_a else bb
        require(bprime, 'product controls collapsed to one wire')
        qq=min(bprime)
        inverse_ops=[(km.q(t),km.q(pp))for t in sorted(aa-{pp})]
        inverse_ops.extend((km.q(t),km.q(qq))for t in sorted(bprime-{qq}))
        if use_a:inverse_ops.append((km.q(pp),km.q(qq)))
        for control,target in inverse_ops:b.cx(control,target)
        out=list(bits(p.fanout&keep))
        require(out, 'product fanout is empty')
        pivot=targets[out[0]]
        require(pivot.id not in(aa|bb), f'pivot {pivot.id} is also a control')
        for k in out[1:]:b.cx(pivot,targets[k])
        b.ccx(km.q(pp),km.q(qq),pivot)
        for k in out[1:]:b.cx(pivot,targets[k])
        for control,target in reversed(inverse_ops):b.cx(control,target)
        product_count+=1;controls_checked+=len(aa|bb)
    for event in schedule['events']:
        transition(event['cache'])
        if event['kind']=='products':
            for index in event['indices']:product(plan.products[index])
        else:
            m=event['monomial'];pure_fanout(m,plan.pure[m])
    transition(0)
    require(not low and len(free)==schedule['capacity'],
            f"low cache not returned: live {sorted(low)} free {len(free)} != {schedule['capacity']}")
    # Nonlinear low terms already streamed after every product. Constant/linear
    # low terms and pure-high terms require no low slot and commute with them.
    for m,fan in plan.pure.items():
        if m<16 and m.bit_count()>=2:continue
        pure_fanout(m,fan)
    b.free(low_extra)
    for m in reversed(high):
        top=1<<(m.bit_length()-1)
        require(m^top in cache and top in cache, f'releasing high monomial {m} without both parents')
        b.del_and(cache[m^top],cache[top],cache[m]);del cache[m]
    b.free(high_pool)
    circuit=b.finish_circuit()
    expected_T=len(high)+computes+len(plan.products)
    expected_Q=(A-1).bit_length()+plan.batch*plan.brot+len(high)+schedule['capacity']
    require(computes==erases==schedule['low_computations'] and product_count==len(plan.products),
            f"emitted counts computes={computes} erases={erases} products={product_count} "
            f"!= schedule {schedule['low_computations']} products {len(plan.products)}")
    require(expected_Q<=128, f'emitted qubit count {expected_Q} exceeds 128')
    require(int(circuit.num_qubits)==expected_Q,
            f'circuit qubits {int(circuit.num_qubits)} != expected {expected_Q}')
    emitted_t=int(circuit.operation_statistics().num_toffoli_like)
    require(emitted_t==expected_T, f'circuit toffolis {emitted_t} != expected {expected_T}')
    return circuit,dict(addresses=A,high_cache=len(high),low_slots=schedule['capacity'],peak_low_live=peak,
        low_computations=computes,low_measurement_erasures=erases,products=product_count,
        T=expected_T,Q=expected_Q,all_measurement_erase_parents_live=True,
        only_redundant_sign_outputs_borrowed=False,borrowed_top_bits=0,promise_top_two_bits_equal=False,no_public_carry=True,borrowed_not_freed=True,control_wire_supports_checked=controls_checked,
        emitted_gate_count_checked=True,native_validation_run=False)
