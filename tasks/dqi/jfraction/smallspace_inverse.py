# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""HMR-first inverse deletion reuses the erased output as its own scaffold.

All transformations are exact. The runtime masks are classical; syndrome
qubits are never measured. At degree12 initialization peaks at24 scratch
qubits, while deletion needs18 including the existing twelve-bit output.
"""


def clear_inverse_hmr(b,source,target,*,field):
    """Delete inverse(source) using target itself for norm and reciprocal."""
    n=len(source);h=n//2;basis=b.bases[n]
    assert n in (6,12) and field.modulus==basis.outer.modulus
    measured=b.alloc_bits(n)
    b.hmr(target,measured)
    low,high=b.alloc_bits(h),b.alloc_bits(h)
    b.bit_store(low,False);b.bit_store(high,False)
    for i in range(h):
        for j in range(n):
            if basis.columns[i]>>j&1:b.cx(measured[j],low[i])
            if basis.columns[h+i]>>j&1:b.cx(measured[j],high[i])
    basis.change_basis(b,source,to_tower=True)
    a,c=source[:h],source[h:]
    norm,reciprocal=target[:h],target[h:]
    b.init_gf2_mul(a,c,target=norm,field=basis.inner)
    basis.add_linear(b,a,norm,basis.square_columns)
    basis.add_linear(b,c,norm,basis.delta_square_columns)
    _,chain=b.init_gf2_inverse_with_scaffold(norm,target=reciprocal,field=basis.inner)
    b.gf2_phase_by_product(a,reciprocal,mask=low,field=basis.inner)
    b.cx(high,low)
    b.gf2_phase_by_product(c,reciprocal,mask=low,field=basis.inner)
    b.del_gf2_inverse_with_scaffold(norm,target=reciprocal,scaffold=chain,field=basis.inner)
    b.free(chain)
    basis.add_linear(b,c,norm,basis.delta_square_columns)
    basis.add_linear(b,a,norm,basis.square_columns)
    b.del_gf2_mul(a,c,target=norm,field=basis.inner)
    basis.change_basis(b,source,to_tower=False)
    b.free(measured+low+high)


def discard_six_scaffold(b,source,scaffold):
    """Discard six scaffold bits of a GF64 inverse while retaining its output."""
    from .common import km
    assert len(source)==len(scaffold)==6
    basis=b.bases[6]
    norm,reciprocal=scaffold[:3],scaffold[3:]
    basis.change_basis(b,source,to_tower=True)
    a,c=source[:3],source[3:]
    b.del_gf2_inverse_with_scaffold(norm,target=reciprocal,scaffold=km.array([]),field=basis.inner)
    b.free(reciprocal)
    basis.add_linear(b,c,norm,basis.delta_square_columns)
    basis.add_linear(b,a,norm,basis.square_columns)
    b.del_gf2_mul(a,c,target=norm,field=basis.inner)
    b.free(norm)
    basis.change_basis(b,source,to_tower=False)


def init_smallspace_inverse(b,source,*,field):
    basis=b.bases[12]
    assert len(source)==12 and field.modulus==basis.outer.modulus
    basis.change_basis(b,source,to_tower=True)
    a,c=source[:6],source[6:]
    norm=b.init_gf2_mul(a,c,field=basis.inner)
    basis.add_linear(b,a,norm,basis.square_columns)
    basis.add_linear(b,c,norm,basis.delta_square_columns)
    reciprocal,chain=b.init_gf2_inverse_with_scaffold(norm,field=basis.inner)
    discard_six_scaffold(b,norm,chain)
    output=b.alloc_qubits(12)
    b.init_gf2_mul(a,reciprocal,target=output[:6],field=basis.inner)
    b.init_gf2_mul(c,reciprocal,target=output[6:],field=basis.inner)
    b.cx(output[6:],output[:6])
    basis.change_basis(b,output,to_tower=False)
    clear_inverse_hmr(b,norm,reciprocal,field=basis.inner)
    b.free(reciprocal)
    basis.add_linear(b,c,norm,basis.delta_square_columns)
    basis.add_linear(b,a,norm,basis.square_columns)
    b.del_gf2_mul(a,c,target=norm,field=basis.inner)
    b.free(norm)
    basis.change_basis(b,source,to_tower=False)
    return output


class SmallSpaceInverseBuilder:
    def __init__(self,builder):self.builder=builder
    def __getattr__(self,name):return getattr(self.builder,name)
    def init_gf2_inverse_with_scaffold(self,source,*,field):
        from .common import km
        # Praxen: fixed paired-v6 norm recycling, without module monkey-patching.
        from .norm_recycle_inverse import init_norm_recycle_inverse
        return init_norm_recycle_inverse(self.builder,source,field=field),km.array([])
    def del_gf2_inverse_with_scaffold(self,source,*,target,scaffold,field):
        assert not len(scaffold)
        clear_inverse_hmr(self.builder,source,target,field=field)
