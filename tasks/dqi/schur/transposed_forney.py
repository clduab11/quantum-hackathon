# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Forney parity via a six-bit transposed product instead of a full inverse."""
import kickmix as km
from .gf4_multiplier import terms
from .crt_multiplier import indices
from .tower_inverse import tower,apply_map,map_ops,linear_xor,product
from .forney_dqi import product_terms
from .tower_inverse import crt_terms


def multiplication_terms(n):
    return terms(n) if n==6 else crt_terms(n)


def transpose_product(b,x,u,target):
    work=b.alloc_qubits(3);a,c,p=work
    for lm,rm,om in multiplication_terms(len(x)):
        xx=km.array([x[j] for j in indices(lm)])
        uu=km.array([u[j] for j in indices(om)])
        dst=km.array([target[j] for j in indices(rm)])
        b.cx(xx,a);b.cx(uu,c);b.init_and(a,c,p)
        b.cx(p,dst);b.del_and(a,c,p);b.cx(uu,c);b.cx(xx,a)
    b.free(work)


def transpose_phase(b,x,u,mask):
    work=b.alloc_qubits(2);a,c=work
    for lm,rm,om in multiplication_terms(len(x)):
        xx=km.array([x[j] for j in indices(lm)])
        uu=km.array([u[j] for j in indices(om)])
        b.cx(xx,a);b.cx(uu,c)
        for j in indices(rm):
            b.push_condition(mask[j]);b.cz(a,c);b.pop_condition()
        b.cx(uu,c);b.cx(xx,a)
    b.free(work)


class TransposedForney:
    def _forney_kernel(self,b,s,d,o,mask):
        gf=self.gf
        info=tower(12)
        columns=info['columns']
        trans_columns=tuple(sum(((columns[i]>>j)&1)<<i for i in range(12)) for j in range(12))
        trans_ops=map_ops(trans_columns)
        tterms=product_terms(gf)
        u=b.alloc_qubits(12)
        v=b.alloc_qubits(6)
        norm=b.alloc_qubits(6)
        parity=b.alloc_qubits(1)[0]
        ladder=b.alloc_qubits(10)
        meas=b.alloc_bits(1)[0]

        def mask_map():
            for k in range(12):
                b.push_condition(mask[k])
                b.cx(km.array([o[i] for i,j in tterms[k]]),km.array([u[j] for i,j in tterms[k]]))
                b.pop_condition()

        apply_map(b,d,info['ops'],True)
        a,c=d[:6],d[6:]
        product(b,a,c,norm)
        linear_xor(b,a,norm,info['square']);linear_xor(b,c,norm,info['musquare'])
        inv,sc=b.init_gf2_inverse_with_scaffold(norm,field=km.GF2Field(6))
        mask_map();apply_map(b,u,trans_ops)
        b.cx(c,a);transpose_product(b,a,u[:6],v);b.cx(c,a)
        transpose_product(b,c,u[6:],v)
        for j in range(6):b.ccx(v[j],inv[j],parity)
        b.x(s)
        b.init_and(s[0],s[1],ladder[0])
        for j in range(1,10):b.init_and(ladder[j-1],s[j+1],ladder[j])
        b.ccz(ladder[9],s[11],parity)
        for j in reversed(range(1,10)):b.del_and(ladder[j-1],s[j+1],ladder[j])
        b.del_and(s[0],s[1],ladder[0]);b.x(s)
        b.hmr(parity,meas)
        b.push_condition(meas)
        b.cz(v,inv)
        b.pop_condition()
        vm=b.alloc_bits(6);b.hmr(v,vm)
        b.cx(c,a);transpose_phase(b,a,u[:6],vm);b.cx(c,a)
        transpose_phase(b,c,u[6:],vm)
        b.bit_store(vm,False);b.free(vm)
        apply_map(b,u,trans_ops,True);mask_map()
        b.del_gf2_inverse_with_scaffold(norm,target=inv,scaffold=sc,field=km.GF2Field(6))
        b.free(inv);b.free(sc)
        linear_xor(b,a,norm,info['square']);linear_xor(b,c,norm,info['musquare'])
        b.del_gf2_mul(a,c,target=norm,field=km.GF2Field(6))
        apply_map(b,d,info['ops'])
        b.bit_store(meas,False);b.free(meas)
        for r in [u,v,norm,km.array([parity]),ladder]:b.free(r)

    def _chien(self,b,Bv,error_mbuc):
        gf=self.gf;t=self.t;T=2*t
        ainv=gf.invert(gf.primitive_element)
        sig=[Bv[T-d] for d in range(t+1)]
        om=[Bv[d] for d in range(t)]
        acc_d,acc_s,acc_o=sig[1],sig[0],om[0]
        odd=[sig[d] for d in range(3,t+1,2)]
        even=[sig[d] for d in range(2,t+1,2)]
        src=km.array([q for r in odd+[sig[1]]+even+om[1:] for q in r])
        dst=km.array([q for r in [acc_d]*len(odd)+[acc_s]*(1+len(even))+[acc_o]*(t-1) for q in r])
        rsrc=km.array(list(reversed(list(src))));rdst=km.array(list(reversed(list(dst))))
        is_error=b.alloc_bits(1)[0]
        num=len(error_mbuc)
        for j,mask in enumerate(error_mbuc):
            xj=gf.pow(ainv,j)
            b.bit_store(is_error,True,control=mask);b.push_condition(is_error)
            b.cx(src,dst)
            if xj!=1:b.gf2_imul(xj,target=acc_o,field=gf)
            self._forney_kernel(b,acc_s,acc_d,acc_o,mask)
            if xj!=1:b.gf2_idiv(xj,target=acc_o,field=gf)
            b.cx(rsrc,rdst)
            b.pop_condition();b.bit_store(is_error,False)
            if j+1<num:
                for d in range(1,t+1):b.gf2_imul(gf.pow(ainv,d),target=sig[d],field=gf)
                for d in range(1,t):b.gf2_imul(gf.pow(ainv,d),target=om[d],field=gf)
        if num>1:
            for d in range(1,t+1):b.gf2_idiv(gf.pow(ainv,d*(num-1)%4095),target=sig[d],field=gf)
            for d in range(1,t):b.gf2_idiv(gf.pow(ainv,d*(num-1)%4095),target=om[d],field=gf)
        b.free(is_error)




