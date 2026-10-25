# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Exact 42-term quadratic x^3 map and phase, from the pinned GF12 tensor."""
from functools import cache

@cache
def terms():
    from .cubic import EvaluationBasis
    from .tower import xor_columns
    basis=EvaluationBasis(12,3);f,g=basis.outer,basis.inner
    coordinates={xor_columns(basis.columns,i):i for i in range(4096)}
    result={}
    for point,weights in zip(basis.points,basis.weights):
        columns=[]
        for bit in range(12):
            packed=coordinates[1<<bit];chunks=[(packed>>(3*i))&7 for i in range(4)]
            value=chunks[-1] if point is None else 0
            if point is not None:
                for i,v in enumerate(chunks):value^=g.mul(v,g.pow(point,i))
            columns.append(value)
        for mask,weight in ((1,4),(2,6),(4,2),(3,1),(7,3),(5,7)):
            left=sum(((x&mask).bit_count()%2)<<i for i,x in enumerate(columns))
            right=sum(((left&f.square(1<<i)).bit_count()%2)<<i for i in range(12))
            packed=sum(g.mul(w,weight)<<(3*i) for i,w in enumerate(weights))
            output=xor_columns(basis.columns,packed)
            key=tuple(sorted((left,right)));result[key]=result.get(key,0)^output
    return tuple((a,c,w) for (a,c),w in result.items() if w)

def _parity(b,source,mask):
    pivot=(mask&-mask).bit_length()-1;changed=[]
    for i in range(12):
        if i!=pivot and mask>>i&1:b.cx(source[i],source[pivot]);changed.append(i)
    return source[pivot],pivot,changed

def xor_cube(b,source,target):
    from .mc4_inverse import affine_operands
    for a,c,weight in terms():
        out=(weight&-weight).bit_length()-1;changed=[]
        for i in range(12):
            if i!=out and weight>>i&1:b.cx(target[out],target[i]);changed.append(i)
        if a==c:
            p,index,changes=_parity(b,source,a);b.cx(p,target[out])
            for i in reversed(changes):b.cx(source[i],source[index])
        else:
            with affine_operands(b,list(source),a<<1,c<<1) as (p,q):b.ccx(p,q,target[out])
        for i in reversed(changed):b.cx(target[out],target[i])

def phase_cube(b,source,mask,*,control=True):
    from .mc4_inverse import affine_operands
    parity=b.alloc_bits(1)
    for a,c,weight in terms():
        b.bit_store(parity[0],False)
        for i in range(12):
            if weight>>i&1:b.cx(mask[i],parity[0])
        if a==c:
            p,index,changes=_parity(b,source,a)
            if control is True:b.cz(parity[0],p)
            else:b.ccz(parity[0],control,p)
            for i in reversed(changes):b.cx(source[i],source[index])
        else:
            with affine_operands(b,list(source),a<<1,c<<1) as (p,q):
                if control is True:b.ccz(parity[0],p,q)
                else:
                    b.push_condition(parity[0]);b.ccz(control,p,q);b.pop_condition()
    b.free(parity)
