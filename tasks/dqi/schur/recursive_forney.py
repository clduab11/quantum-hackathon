# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Contract inverse parity down the complete GF(4096)/GF(64)/GF(8) tower."""
from functools import lru_cache
import kickmix as km
from .tower_inverse import tower,apply_map,map_ops,product,linear_xor
from .forney_dqi import product_terms
from .transposed_forney import TransposedForney,transpose_product,transpose_phase


@lru_cache(None)
def trans_ops(n):
    cols=tower(n)['columns']
    trans=tuple(sum(((cols[i]>>j)&1)<<i for i in range(n)) for j in range(n))
    return map_ops(trans)


def inverse_dot_data(b,source,u):
    n=len(source)
    if n==3:
        inv,sc=b.init_gf2_inverse_with_scaffold(source,field=km.GF2Field(3))
        def cleanup():
            b.del_gf2_inverse_with_scaffold(source,target=inv,scaffold=sc,field=km.GF2Field(3))
            b.free(inv);b.free(sc)
        return u,inv,cleanup
    info=tower(n);m=n//2;field=km.GF2Field(m)
    apply_map(b,source,info['ops'],True);apply_map(b,u,trans_ops(n))
    a,c=source[:m],source[m:]
    norm=b.alloc_qubits(m);v=b.alloc_qubits(m)
    product(b,a,c,norm)
    linear_xor(b,a,norm,info['square']);linear_xor(b,c,norm,info['musquare'])
    b.cx(c,a);transpose_product(b,a,u[:m],v);b.cx(c,a)
    transpose_product(b,c,u[m:],v)
    leaf,inv,inner_cleanup=inverse_dot_data(b,norm,v)
    def cleanup():
        inner_cleanup()
        vm=b.alloc_bits(m);b.hmr(v,vm)
        b.cx(c,a);transpose_phase(b,a,u[:m],vm);b.cx(c,a)
        transpose_phase(b,c,u[m:],vm)
        b.bit_store(vm,False);b.free(vm);b.free(v)
        linear_xor(b,a,norm,info['square']);linear_xor(b,c,norm,info['musquare'])
        b.del_gf2_mul(a,c,target=norm,field=field);b.free(norm)
        apply_map(b,u,trans_ops(n),True);apply_map(b,source,info['ops'])
    return leaf,inv,cleanup


class RecursiveForney(TransposedForney):
    def _forney_kernel(self,b,s,d,o,mask):
        tterms=product_terms(self.gf)
        u=b.alloc_qubits(12)
        def mask_map():
            for k in range(12):
                b.push_condition(mask[k])
                b.cx(km.array([o[i] for i,j in tterms[k]]),km.array([u[j] for i,j in tterms[k]]))
                b.pop_condition()
        mask_map()
        leaf,inv,cleanup=inverse_dot_data(b,d,u)
        parity=b.alloc_qubits(1)[0];ladder=b.alloc_qubits(10);meas=b.alloc_bits(1)[0]
        for j in range(3):b.ccx(leaf[j],inv[j],parity)
        b.x(s);b.init_and(s[0],s[1],ladder[0])
        for j in range(1,10):b.init_and(ladder[j-1],s[j+1],ladder[j])
        b.ccz(ladder[9],s[11],parity)
        for j in reversed(range(1,10)):b.del_and(ladder[j-1],s[j+1],ladder[j])
        b.del_and(s[0],s[1],ladder[0]);b.x(s)
        b.hmr(parity,meas);b.push_condition(meas);b.cz(leaf,inv);b.pop_condition()
        cleanup();mask_map()
        b.bit_store(meas,False);b.free(meas)
        b.free(u);b.free(ladder);b.free(parity)




