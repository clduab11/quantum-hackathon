# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""66T GF4096 inverse output with only18 scratch, by output-norm recycling.

The GF64 norm is inverted in place. Once y=inverse(x) is produced,
Norm(y)=inverse(Norm(x)), so that retained field word is erased from y.
All zero values and every HMR outcome are handled exactly.
"""

def inplace_inverse6(b,source):
    from .common import km
    basis=b.bases[6];native=b.native
    basis.change_basis(native,source,to_tower=True)
    a,c=source[:3],source[3:]
    norm=b.init_gf2_mul(a,c,field=basis.inner)
    basis.add_linear(native,a,norm,basis.square_columns)
    basis.add_linear(native,c,norm,basis.delta_square_columns)
    reciprocal,chain=b.init_gf2_inverse_with_scaffold(norm,field=basis.inner)
    assert len(chain)==0
    native.cx(c,a)
    temporary=b.alloc_qubits(3)
    for word in (a,c):
        b.ixor_gf2_mul(word,reciprocal,target=temporary,field=basis.inner)
        native.swap(word,temporary)
        b.del_gf2_mul(word,norm,target=temporary,field=basis.inner)
    native.free(temporary)
    b.del_gf2_inverse_with_scaffold(reciprocal,target=norm,scaffold=km.array([]),field=basis.inner)
    native.free(norm)
    basis.add_linear(native,a,reciprocal,basis.square_columns)
    basis.add_linear(native,c,reciprocal,basis.delta_square_columns)
    b.del_gf2_mul(a,c,target=reciprocal,field=basis.inner);native.free(reciprocal)
    basis.change_basis(native,source,to_tower=False)


def init_norm_recycle_inverse(b,source,*,field):
    basis=b.bases[12];native=b.native
    assert len(source)==12 and field.modulus==basis.outer.modulus
    basis.change_basis(native,source,to_tower=True)
    a,c=source[:6],source[6:]
    norm=b.init_gf2_mul(a,c,field=basis.inner)
    basis.add_linear(native,a,norm,basis.square_columns)
    basis.add_linear(native,c,norm,basis.delta_square_columns)
    inplace_inverse6(b,norm)
    out=b.alloc_qubits(12)
    b.init_gf2_mul(a,norm,target=out[:6],field=basis.inner)
    b.init_gf2_mul(c,norm,target=out[6:],field=basis.inner)
    native.cx(out[6:],out[:6])
    # The original norm word now equals Norm(out), including x=0.
    basis.add_linear(native,out[:6],norm,basis.square_columns)
    basis.add_linear(native,out[6:],norm,basis.delta_square_columns)
    b.del_gf2_mul(out[:6],out[6:],target=norm,field=basis.inner)
    native.free(norm)
    basis.change_basis(native,out,to_tower=False)
    basis.change_basis(native,source,to_tower=False)
    return out
