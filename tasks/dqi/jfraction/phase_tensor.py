# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Exact inverse phase without a materialized GF4096 inverse output.

Use a classical mask-dependent, invertible linear change of Omega and
two rank-15 trilinear trace phases over GF64. No quantum mask multiplication
or zero-test-chain deletion is introduced. The classical elimination is
fully compiled; it never reads syndrome qubits or branches on a simulator.
"""
from functools import cache


def trace(field, value):
    result=0
    for _ in range(field.degree):
        result ^= value
        value=field.square(value)
    assert result in (0,1)
    return result


@cache
def mask_matrix_columns():
    from .common import km
    from .projection import dual_basis
    f=km.GF2Field(12)
    dual=dual_basis()
    return tuple(tuple(f.mul(d,1<<col) for col in range(12)) for d in dual)


class ClassicalMaskMultiplier:
    """Compile nonzero classical GF4096 multiplication as controlled CX/SWAP.

    Gaussian elimination computes a gate schedule in classical bits. Applying
    its reverse to the quantum word multiplies by the field element dual to
    the input parity mask. Applying it forward restores the quantum word.
    """
    def __init__(self,b,mask):
        self.b=b
        self.matrix=[b.alloc_bits(12) for _ in range(12)]
        self.controls=[]
        self.gates=[]
        columns=mask_matrix_columns()
        for row in self.matrix:b.bit_store(row,False)
        for k in range(12):
            for col in range(12):
                value=columns[k][col]
                for row in range(12):
                    if value>>row&1:b.cx(mask[k],self.matrix[row][col])
        for i in range(12):
            for j in range(i+1,12):
                flag=b.alloc_bits(1)[0]
                b.bit_store(flag,False)
                b.x(self.matrix[i][i])
                b.push_condition(self.matrix[i][i])
                b.bit_store(flag,True,control=self.matrix[j][i])
                b.pop_condition()
                b.x(self.matrix[i][i])
                b.push_condition(flag)
                b.swap(self.matrix[i],self.matrix[j])
                b.pop_condition()
                self.controls.append(flag)
                self.gates.append(('swap',i,j,flag))
            for j in range(12):
                if j==i:continue
                flag=b.alloc_bits(1)[0]
                b.bit_store(flag,False)
                b.cx(self.matrix[j][i],flag)
                b.push_condition(flag)
                b.cx(self.matrix[i],self.matrix[j])
                b.pop_condition()
                self.controls.append(flag)
                self.gates.append(('cx',i,j,flag))

    def apply(self,word,*,inverse=False):
        for name,i,j,flag in self.gates if inverse else reversed(self.gates):
            self.b.push_condition(flag)
            getattr(self.b,name)(word[i],word[j])
            self.b.pop_condition()

    def free(self):
        from .common import km
        for row in self.matrix:self.b.free(row)
        self.b.free(km.array(self.controls))


@cache
def trace_tensor_terms():
    """Rank-15 decomposition of Tr_GF64/F2(A B C), derived from public basis."""
    from .common import km
    from .cubic import EvaluationBasis
    from .tower import xor_columns
    basis=EvaluationBasis(6,2)
    f,g=basis.outer,basis.inner
    coordinates={xor_columns(basis.columns,i):i for i in range(64)}
    terms=[]
    # GF4 product: a0*b0*(1+z) + a1*b1 + (a0+a1)*(b0+b1)*z.
    for point,weights in zip(basis.points,basis.weights):
        eval_columns=[]
        for bit in range(6):
            packed=coordinates[1<<bit]
            chunks=[(packed>>(2*i))&3 for i in range(3)]
            value=chunks[-1] if point is None else 0
            if point is not None:
                for i,x in enumerate(chunks):value^=g.mul(x,g.pow(point,i))
            eval_columns.append(value)
        for inmask,outweight in ((1,3),(2,1),(3,2)):
            amask=sum(((x&inmask).bit_count()%2)<<i for i,x in enumerate(eval_columns))
            packed=sum(g.mul(w,outweight)<<(2*i) for i,w in enumerate(weights))
            coefficient=xor_columns(basis.columns,packed)
            cmask=sum(trace(f,f.mul(coefficient,1<<i))<<i for i in range(6))
            assert amask and cmask
            terms.append((amask,amask,cmask))
    assert len(terms)==15
    return tuple(terms)


def trace_triple_phase(b,a,c,t):
    for masks in trace_tensor_terms():
        pivots=[]
        changes=[]
        for word,mask in zip((a,c,t),masks):
            pivot=(mask&-mask).bit_length()-1
            pivots.append(word[pivot])
            for i in range(6):
                if i!=pivot and mask>>i&1:
                    b.cx(word[i],word[pivot]);changes.append((word[i],word[pivot]))
        b.ccz(*pivots)
        for src,dst in reversed(changes):b.cx(src,dst)


def inverse_phase(b,omega,derivative,flag,mask):
    """Apply (-1)^popcount(mask & omega/derivative), controlled by flag."""
    # The multiplier is invertible only for nonzero masks. Classical scratch
    # allocation does not promise a zero initial value; initialize explicitly.
    nonzero=b.alloc_bits(1)
    b.bit_store(nonzero[0],False)
    b.bit_store(nonzero[0],True,control=mask)
    b.push_condition(nonzero[0])
    transform=ClassicalMaskMultiplier(b,mask)
    transform.apply(omega)
    basis=b.bases[12]
    basis.change_basis(b,omega,to_tower=True)
    basis.change_basis(b,derivative,to_tower=True)
    a,c=derivative[:6],derivative[6:]
    norm=b.init_gf2_mul(a,c,field=basis.inner)
    basis.add_linear(b,a,norm,basis.square_columns)
    basis.add_linear(b,c,norm,basis.delta_square_columns)
    reciprocal,chain=b.init_controlled_inverse(norm,flag)
    # Tr_4096/64((u+v*theta) / (a+c*theta))=(u*c+v*a)/norm.
    trace_triple_phase(b,omega[:6],c,reciprocal)
    trace_triple_phase(b,omega[6:],a,reciprocal)
    b.del_controlled_inverse(norm,flag,target=reciprocal,scaffold=chain)
    b.free(reciprocal+chain)
    basis.add_linear(b,c,norm,basis.delta_square_columns)
    basis.add_linear(b,a,norm,basis.square_columns)
    b.del_gf2_mul(a,c,target=norm,field=basis.inner)
    b.free(norm)
    basis.change_basis(b,derivative,to_tower=False)
    basis.change_basis(b,omega,to_tower=False)
    transform.apply(omega,inverse=True)
    transform.free()
    b.pop_condition()
    b.free(nonzero)


def forney_tensor(b,numerator,denominator_tail,outcomes,*,field):
    from .common import km
    from .merge_kernels import LeanZeroTest
    work=b.alloc_qubits(12)
    flag=b.alloc_qubits(1)[0]
    enabled=b.alloc_bits(1)
    b.bit_store(enabled[0],False)
    zero=LeanZeroTest(b,work)
    omega,derivative=numerator[0],denominator_tail[0]
    def acc_omega():
        for word in numerator[1:]:b.cx(word,omega)
    def acc_derivative():
        for i in range(2,35,2):b.cx(denominator_tail[i],derivative)
    def acc_sigma():
        b.x(work[0])
        for i in range(1,35,2):b.cx(denominator_tail[i],work)
        b.cx(derivative,work)
    positions=min(4095,len(outcomes))
    alpha=field.primitive_element
    for j in range(positions):
        b.bit_store(enabled[0],True,control=outcomes[j])
        b.push_condition(enabled[0])
        acc_omega();acc_derivative();acc_sigma()
        zero.flip_if_equal(work,0,target=flag)
        acc_sigma()
        b.free(work)
        x=field.pow(alpha,-j%4095)
        b.gf2_imul(x,target=omega,field=field)
        inverse_phase(b,omega,derivative,flag,outcomes[j])
        b.gf2_idiv(x,target=omega,field=field)
        work=b.alloc_qubits(12)
        zero.sigma=work
        acc_sigma()
        zero.flip_if_equal(work,0,target=flag)
        acc_sigma();acc_derivative();acc_omega()
        b.pop_condition();b.bit_store(enabled[0],False)
        if j+1<positions:
            for i,word in enumerate(denominator_tail,1):b.gf2_imul(field.pow(alpha,-i%4095),target=word,field=field)
            for i,word in enumerate(numerator):
                if i:b.gf2_imul(field.pow(alpha,-i%4095),target=word,field=field)
    if positions>1:
        for i,word in enumerate(denominator_tail,1):b.gf2_imul(field.pow(alpha,i*(positions-1)%4095),target=word,field=field)
        for i,word in enumerate(numerator):
            if i:b.gf2_imul(field.pow(alpha,i*(positions-1)%4095),target=word,field=field)
    assert zero.chain is None
    b.free(work+km.array([flag])+enabled)
