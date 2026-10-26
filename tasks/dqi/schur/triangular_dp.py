# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Optimal splits for the exact in-place unit Toeplitz product.

Each candidate splits into two recursive diagonal blocks and the existing
trimmed/transposed bilinear middle product. No arithmetic identity changes.
"""
from functools import lru_cache
from .trimmed_middle import TrimmedArithmetic

@lru_cache(None)
def plan(n,start,q,nonzero):
    if n<=1 or start>=n:return 0,0
    best=None
    for cut in range(1,n):
        skip=max(0,start-cut)
        width=q*max(nonzero,default=0)-skip
        lo=min(cut,max(0,width));hi=min(n-cut-skip,max(0,width))
        if lo<=0 or hi<=0:middle=0
        else:
            pairs=sum(1 for i in range(hi) for j in range(lo)
                      if (lo+skip+i-j)%q==0 and (lo+skip+i-j)//q in nonzero)
            middle=min(pairs,lo+hi-1)
        cost=plan(cut,start,q,nonzero)[0]+plan(n-cut,max(0,start-cut),q,nonzero)[0]+middle
        # Prefer balanced trees on ties to limit Python recursion and Clifford work.
        key=(cost,abs(2*cut-n),cut)
        if best is None or key<best[0]:best=(key,cut)
    return best[0][0],best[1]

class DPArithmetic(TrimmedArithmetic):
    def triangular(self,A,q,target,inverse=False):
        return self.triangular_suffix(A,q,target,0,inverse)
    def triangular_suffix(self,A,q,target,start,inverse=False):
        if len(target)<=1 or start>=len(target):return
        nz=tuple(j for j in range(1,len(A)) if tuple(A[j]) not in self.known_zero)
        if not nz:return
        _,cut=plan(len(target),start,q,nz)
        lo,hi=target[:cut],target[cut:]
        skip=max(0,start-cut)
        if inverse:
            self.triangular_suffix(A,q,lo,start,True)
            self.offset_middle(A,q,lo,hi[skip:],skip)
            self.triangular_suffix(A,q,hi,max(0,start-cut),True)
        else:
            self.triangular_suffix(A,q,hi,max(0,start-cut))
            self.offset_middle(A,q,lo,hi[skip:],skip)
            self.triangular_suffix(A,q,lo,start)
