# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Low-cost binary-field inversion via quadratic subfield towers.

GF(4096) -> GF(64) -> GF(8). The norm identity in a quadratic extension
x=a+b*t, t^2+t=mu, gives x^-1=((a+b)+b*t)/(a^2+a*b+mu*b^2).
Multiplications use 45, 18 and 6 ANDs; GF(8) inversion is quadratic (3 ANDs).
The resulting GF(4096) inverse costs 75 Toffolis and keeps 18 scaffold qubits.
"""
from functools import lru_cache
import numpy as np
import kickmix as km
from .crt_multiplier import indices,rem,mul,div,inverse,small_terms,terms12,FullCRTBuilder

@lru_cache(None)
def crt_terms(n):
    if n==12:return terms12()
    if n==3:return small_terms(km.GF2Field(3).modulus)
    assert n==6
    modulus=km.GF2Field(n).modulus;mods=[2,3,7,11,13]
    P=1
    for m in mods:P=mul(P,m)
    result=[]
    def transform(v,cols):
        out=0
        for i in indices(v):out^=cols[i]
        return out
    for m in mods:
        d=m.bit_length()-1;q=div(P,m);E=mul(q,inverse(rem(q,m),m))
        inp=[sum(((rem(1<<i,m)>>j)&1)<<i for i in range(n)) for j in range(d)]
        out=[rem(rem(E<<j,P),modulus) for j in range(d)]
        for l,r,o in ([(1,1,1)] if d==1 else small_terms(m)):
            result.append((transform(l,inp),transform(r,inp),transform(o,out)))
    result.append((1<<(n-1),1<<(n-1),rem(P,modulus)))
    assert len(result)==18
    return tuple(result)


def product(b,lhs,rhs,target):
    work=b.alloc_qubits(3);l,r,p=work
    for lm,rm,om in crt_terms(len(lhs)):
        ll=km.array([lhs[i] for i in indices(lm)]);rr=km.array([rhs[i] for i in indices(rm)]);oo=km.array([target[i] for i in indices(om)])
        b.cx(ll,l);b.cx(rr,r);b.init_and(l,r,p);b.cx(p,oo);b.del_and(l,r,p);b.cx(rr,r);b.cx(ll,l)
    b.free(work)


def linear_xor(b,source,target,columns):
    for i,value in enumerate(columns):
        out=km.array([target[j] for j in indices(value)])
        if len(out):b.cx(source[i],out)


def map_ops(columns):
    n=len(columns);rows=[sum(((columns[i]>>j)&1)<<i for i in range(n)) for j in range(n)];ops=[]
    for j in range(n):
        pivot=next(i for i in range(j,n) if rows[i]>>j&1)
        if pivot!=j:rows[j],rows[pivot]=rows[pivot],rows[j];ops.append(('swap',j,pivot))
        for i in range(n):
            if i!=j and rows[i]>>j&1:rows[i]^=rows[j];ops.append(('cx',j,i))
    return tuple(reversed(ops))


def apply_map(b,reg,ops,inverse=False):
    for op,i,j in (reversed(ops) if inverse else ops):getattr(b,op)(reg[i],reg[j])

@lru_cache(None)
def tower(n):
    assert n in [6,12]
    f=km.GF2Field(n);m=n//2;sub=km.GF2Field(m)
    # Embed the subfield's polynomial generator into the larger field.
    def eval_poly(poly,x):
        out=0
        for i in reversed(range(poly.bit_length())):out=f.mul(out,x)^((poly>>i)&1)
        return out
    root=next(x for x in range(2,1<<n) if eval_poly(sub.modulus,x)==0)
    basis=[f.pow(root,i) for i in range(m)]
    embeds=[]
    for a in range(1<<m):
        v=0
        for i in indices(a):v^=basis[i]
        embeds.append(v)
    # Small mu with absolute trace 1; t solves t^2+t=mu in the extension.
    for mu in range(1,1<<m):
        trace=0;v=mu
        for _ in range(m):trace^=v;v=sub.mul(v,v)
        if trace!=1:continue
        candidates=[x for x in range(1<<n) if f.mul(x,x)^x==embeds[mu]]
        if candidates:
            t=candidates[0];break
    columns=tuple(basis+[f.mul(t,v) for v in basis])
    ops=map_ops(columns)
    square=tuple(sub.mul(1<<i,1<<i) for i in range(m))
    musquare=tuple(sub.mul(mu,v) for v in square)
    return dict(n=n,m=m,mu=mu,root=root,t=t,columns=columns,ops=ops,square=square,musquare=musquare)


def tiny_inverse(b,source,target):
    f=km.GF2Field(3)
    values=[f.pow(x,6) for x in range(8)]
    linear=[values[1<<i] for i in range(3)]
    linear_xor(b,source,target,linear)
    p=b.alloc_qubits(1)[0]
    for i in range(3):
        for j in range(i):
            out=values[(1<<i)|(1<<j)]^values[1<<i]^values[1<<j]
            b.init_and(source[i],source[j],p)
            b.cx(p,km.array([target[k] for k in indices(out)]))
            b.del_and(source[i],source[j],p)
    b.free(km.array([p]))


def init_inverse(b,source,target):
    n=len(source)
    b.reset(target)
    if n==3:
        tiny_inverse(b,source,target)
        return km.array([])
    info=tower(n);m=info['m'];a,c=source[:m],source[m:]
    apply_map(b,source,info['ops'],True)
    norm=b.alloc_qubits(m);invnorm=b.alloc_qubits(m);b.reset(norm)
    product(b,a,c,norm)
    linear_xor(b,a,norm,info['square']);linear_xor(b,c,norm,info['musquare'])
    inner=init_inverse(b,norm,invnorm)
    b.cx(c,a);product(b,a,invnorm,target[:m]);b.cx(c,a)
    product(b,c,invnorm,target[m:])
    apply_map(b,target,info['ops']);apply_map(b,source,info['ops'])
    return km.array([*norm,*invnorm,*inner])


def del_inverse(b,source,target,scaffold):
    n=len(source)
    if n==3:
        f=km.GF2Field(3);values=[f.pow(x,6) for x in range(8)]
        measurements=b.alloc_bits(3);b.hmr(target,measurements)
        for k in range(3):
            b.push_condition(measurements[k])
            for i in range(3):
                if values[1<<i]>>k&1:b.z(source[i])
                for j in range(i):
                    q=values[(1<<i)|(1<<j)]^values[1<<i]^values[1<<j]
                    if q>>k&1:b.cz(source[i],source[j])
            b.pop_condition()
        b.bit_store(measurements,False);b.free(measurements)
        return
    info=tower(n);m=info['m'];field=km.GF2Field(m)
    norm,invnorm,inner=scaffold[:m],scaffold[m:2*m],scaffold[2*m:]
    apply_map(b,source,info['ops'],True);apply_map(b,target,info['ops'],True)
    a,c=source[:m],source[m:]
    b.cx(c,a);b.del_gf2_mul(a,invnorm,target=target[:m],field=field);b.cx(c,a)
    b.del_gf2_mul(c,invnorm,target=target[m:],field=field)
    del_inverse(b,norm,invnorm,inner)
    linear_xor(b,a,norm,info['square']);linear_xor(b,c,norm,info['musquare'])
    b.del_gf2_mul(a,c,target=norm,field=field)
    apply_map(b,source,info['ops']);apply_map(b,target,info['ops'])


class TowerBuilder(FullCRTBuilder):
    def init_gf2_inverse_with_scaffold(self,input,*,target='alloc',field=None):
        if len(input) not in [3,6,12]:return super().init_gf2_inverse_with_scaffold(input,target=target,field=field)
        if isinstance(target,str):target=self.b.alloc_qubits(len(input))
        scaffold=init_inverse(self.b,input,target)
        return target,scaffold
    def del_gf2_inverse_with_scaffold(self,input,*,target,scaffold,field=None):
        if len(input) not in [3,6,12]:return super().del_gf2_inverse_with_scaffold(input,target=target,scaffold=scaffold,field=field)
        del_inverse(self.b,input,target,scaffold)
    # FullCRTBuilder division packs [inverse, chain] and calls these overrides.


