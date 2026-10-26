# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""A 45-AND GF(2^12) bilinear multiplier from polynomial CRT.

Reconstruct degree <=22 products from all irreducibles of degrees 1..4
(total degree 22), plus the leading coefficient. Small-field Karatsuba
multipliers are flattened into binary linear forms, so circuit workspace
is independent of the number of CRT moduli.
"""
from functools import lru_cache
import re
import kickmix as km

def deg(p): return p.bit_length()-1

def rem(p,m):
    while deg(p)>=deg(m): p ^= m << (deg(p)-deg(m))
    return p

def mul(a,b):
    c=0
    while b:
        if b&1:c^=a
        a<<=1;b>>=1
    return c

def div(a,b):
    q=0
    while deg(a)>=deg(b):
        s=deg(a)-deg(b);q^=1<<s;a^=b<<s
    assert a==0
    return q

def inverse(a,m):
    for b in range(1,1<<deg(m)):
        if rem(mul(a,b),m)==1:return b
    raise ValueError('not invertible')

def indices(mask):
    return [i for i in range(mask.bit_length()) if mask>>i&1]

def small_terms(modulus):
    d=deg(modulus)
    if d==3:
        # Six symmetric products recover all degree-four convolution coefficients.
        result=[]
        for i in range(3):
            out=rem(1<<(2*i),modulus)
            for j in range(3):
                if j!=i:out^=rem(1<<(i+j),modulus)
            result.append((1<<i,1<<i,out))
        for i in range(3):
            for j in range(i):result.append(((1<<i)|(1<<j),(1<<i)|(1<<j),rem(1<<(i+j),modulus)))
        return result
    b=km.CircuitBuilder(); a=b.alloc_qubits(d);c=b.alloc_qubits(d);t=b.alloc_qubits(d)
    b.ixor_gf2_mul(a,c,target=t,field=km.GF2Field(d,modulus=modulus))
    circuit=b.finish_circuit()
    symbols=[1<<i if i<2*d else 0 for i in range(circuit.num_qubits)]
    terms=[]
    for line in str(circuit).splitlines():
        op=line.split()[0]
        if op=='INFO_TAG':continue
        qs=[int(x) for x in re.findall(r'q(\d+)',line)]
        if op=='CX':symbols[qs[1]]^=symbols[qs[0]]
        elif op=='SWAP':symbols[qs[0]],symbols[qs[1]]=symbols[qs[1]],symbols[qs[0]]
        elif op=='CCX':
            l,r=symbols[qs[0]],symbols[qs[1]]
            if l>>d: l,r=r,l
            assert l<1<<d and r<1<<(2*d) and r&((1<<d)-1)==0
            terms.append((l,r>>d));symbols[qs[2]] ^=1<<(2*d+len(terms)-1)
        else:raise ValueError(line)
    result=[]
    for i,(l,r) in enumerate(terms):
        out=sum(((symbols[2*d+j]>>(2*d+i))&1)<<j for j in range(d))
        result.append((l,r,out))
    return result

@lru_cache(None)
def terms12(modulus=None):
    modulus=modulus or km.GF2Field(12).modulus
    mods=[2,3,7,11,13,19,25,31]
    P=1
    for m in mods:P=mul(P,m)
    terms=[]
    for m in mods:
        d=deg(m);q=div(P,m);E=mul(q,inverse(rem(q,m),m))
        input_masks=[sum(((rem(1<<i,m)>>j)&1)<<i for i in range(12)) for j in range(d)]
        output_values=[rem(rem(E<<j,P),modulus) for j in range(d)]
        local=[(1,1,1)] if d==1 else small_terms(m)
        def transform(v,cols):
            s=0
            for j in indices(v):s^=cols[j]
            return s
        for l,r,o in local:terms.append((transform(l,input_masks),transform(r,input_masks),transform(o,output_values)))
    terms.append((1<<11,1<<11,rem(P,modulus)))
    assert len(terms)==45
    return terms


def apply(b,lhs,rhs,target,control=True):
    """XOR product into an arbitrary target, restoring inputs and workspace."""
    if control is False:return
    if control is not True:
        gated=b.alloc_qubits(12)
        b.init_and(control,lhs,gated)
        apply(b,gated,rhs,target)
        b.del_and(control,lhs,gated);b.free(gated)
        return
    work=b.alloc_qubits(3);l,r,p=work
    for lm,rm,om in terms12():
        ll=km.array([lhs[i] for i in indices(lm)])
        rr=km.array([rhs[i] for i in indices(rm)])
        oo=km.array([target[i] for i in indices(om)])
        b.cx(ll,l);b.cx(rr,r)
        b.init_and(l,r,p);b.cx(p,oo);b.del_and(l,r,p)
        b.cx(rr,r);b.cx(ll,l)
    b.free(work)


class CRTBuilder:
    """Delegate to kickmix, substituting only degree-12 XOR multiplications."""
    def __init__(self,b):self.b=b
    def __getattr__(self,name):return getattr(self.b,name)
    def ixor_gf2_mul(self,lhs,rhs,*,target,field=None,control=True):
        if len(target)==12 and (field is None or field.modulus==km.GF2Field(12).modulus):
            return apply(self.b,lhs,rhs,target,control)
        return self.b.ixor_gf2_mul(lhs,rhs,target=target,field=field,control=control)




@lru_cache(None)
def frobenius_operations(power):
    """CNOT/SWAP synthesis of the invertible binary Frobenius map."""
    f=km.GF2Field(12)
    cols=[f.pow(1<<i,1<<power) for i in range(12)]
    rows=[sum(((cols[i]>>j)&1)<<i for i in range(12)) for j in range(12)]
    ops=[]
    for j in range(12):
        pivot=next(i for i in range(j,12) if rows[i]>>j&1)
        if pivot!=j:rows[j],rows[pivot]=rows[pivot],rows[j];ops.append(('swap',j,pivot))
        for i in range(12):
            if i!=j and rows[i]>>j&1:rows[i]^=rows[j];ops.append(('cx',j,i))
    assert rows==[1<<i for i in range(12)]
    return tuple(reversed(ops))


def frobenius(b,reg,power,inverse=False):
    ops=frobenius_operations(power)
    for op,i,j in (reversed(ops) if inverse else ops):getattr(b,op)(reg[i],reg[j])


class FullCRTBuilder(CRTBuilder):
    """Use the CRT multiplier in Itoh–Tsujii inversion and division too."""
    def init_gf2_inverse_with_scaffold(self,input,*,target='alloc',field=None):
        if len(input)!=12:return self.b.init_gf2_inverse_with_scaffold(input,target=target,field=field)
        b=self.b
        if isinstance(target,str):target=b.alloc_qubits(12)
        scaffold=b.alloc_qubits(48)
        steps=[scaffold[i:i+12] for i in range(0,48,12)]
        b.reset(target);b.reset(scaffold)
        for left,right,power,out in [(input,input,1,steps[0]),(steps[0],steps[0],2,steps[1]),(steps[1],input,1,steps[2]),(steps[2],steps[2],5,steps[3])]:
            b.cx(left,target);frobenius(b,target,power)
            apply(b,target,right,out)
            frobenius(b,target,power,True);b.cx(left,target)
        frobenius(b,steps[3],1);apply(b,steps[3],input,target);frobenius(b,steps[3],1,True)
        frobenius(b,target,1)
        return target,scaffold

    def del_gf2_inverse_with_scaffold(self,input,*,target,scaffold,field=None):
        if len(input)!=12:return self.b.del_gf2_inverse_with_scaffold(input,target=target,scaffold=scaffold,field=field)
        b=self.b;steps=[scaffold[i:i+12] for i in range(0,48,12)]
        frobenius(b,target,1,True)
        frobenius(b,steps[3],1);b.del_gf2_mul(steps[3],input,target=target,field=field);frobenius(b,steps[3],1,True)
        seq=[(input,input,1,steps[0]),(steps[0],steps[0],2,steps[1]),(steps[1],input,1,steps[2]),(steps[2],steps[2],5,steps[3])]
        for left,right,power,out in reversed(seq):
            b.cx(left,target);frobenius(b,target,power)
            b.del_gf2_mul(target,right,target=out,field=field)
            frobenius(b,target,power,True);b.cx(left,target)

    def init_gf2_div_with_scaffold(self,lhs,rhs,*,target='alloc',field=None):
        if len(lhs)!=12:return self.b.init_gf2_div_with_scaffold(lhs,rhs,target=target,field=field)
        b=self.b
        if isinstance(target,str):target=b.alloc_qubits(12)
        inv,chain=self.init_gf2_inverse_with_scaffold(rhs,field=field)
        b.reset(target);apply(b,lhs,inv,target)
        return target,km.array([*inv,*chain])

    def del_gf2_div_with_scaffold(self,lhs,rhs,*,target,scaffold,field=None):
        if len(lhs)!=12:return self.b.del_gf2_div_with_scaffold(lhs,rhs,target=target,scaffold=scaffold,field=field)
        inv,chain=scaffold[:12],scaffold[12:]
        self.b.del_gf2_mul(lhs,inv,target=target,field=field)
        self.del_gf2_inverse_with_scaffold(rhs,target=inv,scaffold=chain,field=field)


