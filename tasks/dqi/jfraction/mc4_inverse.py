# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Exact4-AND circuit for c*inverse_GF8(x), no held scaffold.

Fixed affine-XOR/AND program synthesized and checked on all16 inputs.
Three ANDs were UNSAT in the same exhaustive SAT model. Runtime needs no
solver. Delayed outer inverse-output allocation hides the transient4 gates.
"""
from contextlib import contextmanager

AND_INPUTS=((4,25),(3,46),(113,106),(7,114))
OUTPUTS=(166,336,316)


@contextmanager
def affine_operands(b,variables,left,right):
    """Compute two independent affine parities in place, then restore wires."""
    changes=[]
    p=next(i for i in range(len(variables)) if left>>(i+1)&1)
    for i,q in enumerate(variables):
        if i!=p and left>>(i+1)&1:
            b.cx(q,variables[p]);changes.append(('cx',q,variables[p]))
    if left&1:b.x(variables[p]);changes.append(('x',variables[p]))
    if right>>(p+1)&1:right^=left^(1<<(p+1))
    q=next(i for i in range(len(variables)) if i!=p and right>>(i+1)&1)
    for i,wire in enumerate(variables):
        if i!=q and right>>(i+1)&1:
            b.cx(wire,variables[q]);changes.append(('cx',wire,variables[q]))
    if right&1:b.x(variables[q]);changes.append(('x',variables[q]))
    try:yield variables[p],variables[q]
    finally:
        for gate in reversed(changes):getattr(b,gate[0])(*gate[1:])


def init_mc4(b,input,control,*,target='alloc'):
    out=b.alloc_qubits(3) if isinstance(target,str) and target=='alloc' else target
    b.reset(out)
    variables=[control,*input];gates=[]
    for left,right in AND_INPUTS:
        gate=b.alloc_qubits(1)[0]
        with affine_operands(b,variables,left,right) as (a,c):b.init_and(a,c,gate)
        gates.append(gate);variables.append(gate)
    for bit,mask in enumerate(OUTPUTS):
        if mask&1:b.x(out[bit])
        for i,wire in enumerate(variables):
            if mask>>(i+1)&1:b.cx(wire,out[bit])
    for i in reversed(range(4)):
        left,right=AND_INPUTS[i]
        with affine_operands(b,variables[:4+i],left,right) as (a,c):b.del_and(a,c,gates[i])
        b.free(gates[i])
    return out


def builder_class():
    from .common import km
    from .zero_mask_inverse import builder_class as zero_class
    class MC4InverseBuilder(zero_class()):
        def init_controlled_inverse(self,input,control,*,target='alloc'):
            n=len(input)
            if n==3 and isinstance(control,km.q):
                return init_mc4(self.native,input,control,target=target),km.array([])
            if n not in (6,12) or not isinstance(target,str) or target!='alloc':
                return super().init_controlled_inverse(input,control,target=target)
            b=self.native;basis=self.bases[n];h=n//2
            basis.change_basis(b,input,to_tower=True)
            a,c=input[:h],input[h:]
            norm=self.init_gf2_mul(a,c,field=basis.inner)
            basis.add_linear(b,a,norm,basis.square_columns)
            basis.add_linear(b,c,norm,basis.delta_square_columns)
            reciprocal,chain=self.init_controlled_inverse(norm,control)
            out=b.alloc_qubits(n)
            b.reset(out)
            self.init_gf2_mul(a,reciprocal,target=out[:h],field=basis.inner)
            self.init_gf2_mul(c,reciprocal,target=out[h:],field=basis.inner)
            b.cx(out[h:],out[:h])
            basis.change_basis(b,out,to_tower=False)
            basis.change_basis(b,input,to_tower=False)
            return out,norm+reciprocal+chain
    return MC4InverseBuilder
