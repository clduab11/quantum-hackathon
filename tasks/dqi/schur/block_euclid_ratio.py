# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Exact quotient-block extraction from a compact monic Euclidean state.

With P B+R Bprev=p*x^N, put T=reverse(R), A=reverse(B), D=reverse(Bprev).
The local quotient series is T*A/(p+z^2*T*D). Its first 2b coefficients
determine b generic degree-one Euclidean steps, independent of the full degree.
This is a classical identity test, not a completed reversible decoder.
"""
import json,random
from pathlib import Path
from .compact_euclid import mul,inv,product,xor


def trim(a):
    a=list(a)
    while a and not a[-1]:a.pop()
    return a


def series_product(a,b,n):
    return (product(a,b)+[0]*n)[:n]


def series_divide(a,b,n):
    if not b or not b[0]:raise ValueError('zero series pivot')
    out=[0]*n;bi=inv(b[0])
    for i in range(n):
        value=a[i] if i<len(a) else 0
        for j in range(1,min(i,len(b)-1)+1):value^=mul(b[j],out[i-j])
        out[i]=mul(value,bi)
    return out


def normalized_step(P,R,Bprev,B):
    if not P or not R or len(P)!=len(R)+1:raise ValueError('degree gap or completion')
    beta=mul(R[-1],inv(P[-1]))
    alpha=mul(P[-2],inv(P[-1]))^mul(R[-2] if len(R)>1 else 0,inv(R[-1]))
    newR=trim(xor([mul(beta,v) for v in P],product([alpha,1],R)))
    newB=trim(xor([mul(beta,v) for v in Bprev],product([alpha,1],B)))
    return list(R),newR,list(B),newB,(alpha,beta)


def quotient_block(P,R,b):
    steps=[]
    for _ in range(b):
        P,R,_,_,q=normalized_step(P,R,[],[1]);steps.append(q)
    return steps


def local_series(R,Bprev,B,p,b):
    n=2*b;T=list(reversed(R))[:n];A=list(reversed(B));D=list(reversed(Bprev))
    numerator=series_product(T,A,n)
    denominator=[p,0]+series_product(T,D,max(0,n-2))
    return series_divide(numerator,denominator[:n],n)




