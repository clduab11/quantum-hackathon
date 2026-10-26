# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Symmetric bilinear multiplication over GF(4): 15 ANDs for GF(64), 42 for GF(4096).

CRT for polynomial products over GF(4), evaluating at four rational points
and (for degree-six inputs) three irreducible quadratic points, plus infinity.
All evaluation, interpolation and field-basis changes are binary linear maps.
"""
from functools import lru_cache
from itertools import combinations
import kickmix as km
from .crt_multiplier import small_terms,indices
from .tower_inverse import map_ops
F4=km.GF2Field(2)

def degree(p):return (p.bit_length()+1)//2-1

def scalar(p,a):
    out=0
    for i in range(degree(p)+1):out |= F4.mul((p>>(2*i))&3,a)<<(2*i)
    return out

def multiply(a,b):
    out=0
    for i in range(degree(b)+1):out ^= scalar(a,(b>>(2*i))&3)<<(2*i)
    return out

def remainder(a,m):
    dm=degree(m);lead=(m>>(2*dm))&3
    while a and degree(a)>=dm:
        da=degree(a);factor=F4.div((a>>(2*da))&3,lead)
        a ^= scalar(m,factor)<<(2*(da-dm))
    return a

def quotient(a,b):
    q=0
    while a and degree(a)>=degree(b):
        d=degree(a)-degree(b);factor=F4.div((a>>(2*degree(a)))&3,(b>>(2*degree(b)))&3)
        q ^=factor<<(2*d);a ^=scalar(b,factor)<<(2*d)
    assert not a
    return q

def invert(a,m):
    for b in range(1,1<<(2*degree(m))):
        if remainder(multiply(a,b),m)==1:return b
    raise ValueError('not invertible')

def map_value(value,ops,inverse=False):
    for op,i,j in (reversed(ops) if inverse else ops):
        if op=='cx':value ^= ((value>>i)&1)<<j
        elif ((value>>i)^(value>>j))&1:value^=(1<<i)|(1<<j)
    return value

def local_terms(modulus):
    d=degree(modulus)
    basic=small_terms(F4.modulus)
    if d==1:return basic
    assert d==2
    p=(modulus>>2)&3;q=modulus&3
    result=[]
    for kind in range(3):
        for l,r,o in basic:
            if kind==0:ll,rr,oo=l,r,o|(o<<2)
            elif kind==1:ll,rr,oo=l<<2,r<<2,F4.mul(q,o)|(F4.mul(1^p,o)<<2)
            else:ll,rr,oo=l|(l<<2),r|(r<<2),o<<2
            result.append((ll,rr,oo))
    return result


def candidates(n,quadmods):
    f=km.GF2Field(n);d=n//2
    root=next(x for x in range(2,1<<n) if f.mul(x,x)^x^1==0)
    theta=f.primitive_element
    embed=[0,1,root,root^1]
    columns=tuple(f.mul(embed[1<<j],f.pow(theta,i)) for i in range(d) for j in range(2))
    ops=map_ops(columns)
    def evaluate(poly):
        out=0
        for i in reversed(range(degree(poly)+1)):out=f.mul(out,theta)^embed[(poly>>(2*i))&3]
        return out
    mods=[4|a for a in range(4)]+list(quadmods)
    P=1
    for m in mods:P=multiply(P,m)
    assert degree(P)==2*d-2
    result=[]
    def transform(v,cols):
        out=0
        for i in indices(v):out^=cols[i]
        return out
    for m in mods:
        k=degree(m);q=quotient(P,m);E=multiply(q,invert(remainder(q,m),m))
        # Binary basis of the input is the host's native GF(2^n) basis.
        input_values=[remainder(map_value(1<<i,ops,True),m) for i in range(n)]
        input_masks=[sum(((v>>j)&1)<<i for i,v in enumerate(input_values)) for j in range(2*k)]
        out=[evaluate(remainder(multiply(E,1<<j),P)) for j in range(2*k)]
        for l,r,o in local_terms(m):result.append((transform(l,input_masks),transform(r,input_masks),transform(o,out)))
    # The leading coefficient at infinity restores the omitted degree-(2d-2) term.
    input_values=[map_value(1<<i,ops,True)>>(2*(d-1)) for i in range(n)]
    masks=[sum(((v>>j)&1)<<i for i,v in enumerate(input_values)) for j in range(2)]
    out=[evaluate(scalar(P,1<<j)) for j in range(2)]
    for l,r,o in small_terms(F4.modulus):result.append((transform(l,masks),transform(r,masks),transform(o,out)))
    return tuple(result)

@lru_cache(None)
def terms(n):
    if n==6:
        result=candidates(6,())
        assert len(result)==15
        return result
    assert n==12
    quadratics=[16|(p<<2)|q for p in range(4) for q in range(1,4) if all(remainder(16|(p<<2)|q,4|a) for a in range(4))]
    assert len(quadratics)==6
    # Choose the exact construction with the least Clifford work.
    choices=[candidates(12,c) for c in combinations(quadratics,3)]
    result=min(choices,key=lambda ts:sum(l.bit_count()+r.bit_count()+o.bit_count() for l,r,o in ts))
    assert len(result)==42
    return result


