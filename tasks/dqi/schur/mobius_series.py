# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Low-workspace Möbius map T -> A*T/(p+z^2*D*T) modulo z^n.

A,D have constant one, p is nonzero. Conjugating a single unit-series inverse
avoids inversions of T[0], which can be zero. This research circuit uses the
attributed upstream field/gate generator; it is not a submission decoder.
"""
import json,time
from pathlib import Path
import numpy as np
import kickmix as km
from .import_published import load
from .series_inverse import SeriesArithmetic
from .block_euclid_ratio import series_divide,series_product



class BoundedArithmetic(SeriesArithmetic):
    def __init__(self,*args):
        super().__init__(*args);self.known_zero=set()
    def spec(self,terms):
        return super().spec([(c,w,q) for c,w,q in terms if tuple(w) not in self.known_zero])
    def sparse_middle(self,A,q,low,high):
        m=self.m;n=len(low)+len(high)-1;pts,I=m.vinv(n)
        pairs=[(i,j,(len(low)+i-j)//q) for i in range(len(high)) for j in range(len(low))
               if len(low)+i-j>=q and (len(low)+i-j)%q==0 and
               (len(low)+i-j)//q<len(A) and tuple(A[(len(low)+i-j)//q]) not in self.known_zero]
        if len(pairs)<=n:
            for i,j,h in pairs:
                self.product(self.spec([(1,A[h],q)]),self.spec([(1,low[j],1)]),lambda tb,i=i:[high[i][b] for b in tb])
            return
        for a,point in enumerate(pts):
            left=self.spec([(I[j-1][a],A[j//q],q) for j in range(q,n+1,q) if j//q<len(A)])
            if not any(left):continue
            right=self.spec([(m.gpow(point,j),word,1) for j,word in enumerate(reversed(low))])
            powers=[m.gpow(point,i) for i in range(len(high))]
            def targets(tb):
                return [high[i][k] for i,power in enumerate(powers) for k in m.bitlist(m.gmul(power,m.tmask(tb)),12)]
            self.product(left,right,targets)

    def triangular_suffix(self,A,q,target,start,inverse=False):
        """Multiply only the suffix by a unit series, preserving its prefix.

        This is the lower triangular block [[I,0],[M,A_tail]]. Its inverse
        also leaves the prefix fixed; the recursion uses the original low
        coefficients before each forward cross update and after its inverse.
        """
        if len(target)<=1 or start>=len(target):return
        if start<=0:
            self.triangular(A,q,target,inverse);return
        cut=len(target)//2;lo,hi=target[:cut],target[cut:]
        def middle():
            skip=max(0,start-cut)
            if not skip:self.sparse_middle(A,q,lo,hi);return
            m=self.m;n=len(lo)+len(hi)-1
            pairs=[(i,j,(len(lo)+i-j)//q)
                   for i in range(skip,len(hi)) for j in range(len(lo))
                   if len(lo)+i-j>=q and (len(lo)+i-j)%q==0
                   and (len(lo)+i-j)//q<len(A)
                   and tuple(A[(len(lo)+i-j)//q]) not in self.known_zero]
            if len(pairs)<=n:
                for i,j,h in pairs:
                    self.product(self.spec([(1,A[h],q)]),self.spec([(1,lo[j],1)]),lambda tb,i=i:[hi[i][b] for b in tb])
                return
            pts,I=m.vinv(n)
            for a,point in enumerate(pts):
                left=self.spec([(I[j-1][a],A[j//q],q) for j in range(q,n+1,q) if j//q<len(A)])
                if not any(left):continue
                right=self.spec([(m.gpow(point,j),word,1) for j,word in enumerate(reversed(lo))])
                powers=[m.gpow(point,i) for i in range(skip,len(hi))]
                def targets(tb):
                    return [hi[i][k] for i,power in zip(range(skip,len(hi)),powers)
                            for k in m.bitlist(m.gmul(power,m.tmask(tb)),12)]
                self.product(left,right,targets)
        if inverse:
            self.triangular_suffix(A,q,lo,start,True);middle()
            self.triangular_suffix(A,q,hi,max(0,start-cut),True)
        else:
            self.triangular_suffix(A,q,hi,max(0,start-cut));middle()
            self.triangular_suffix(A,q,lo,start)


def apply(m,E,math,A,D,p,T,inverse=False,p_is_inverse=False):
    def scale(inv):
        with m.inv_word(E,p) as iv,m.opened(E,'mobius_product',12) as product:
            scale_inverse=bool(inv)^bool(p_is_inverse)
            for word in T:m.mon_slot(E,word,p if scale_inverse else iv,iv if scale_inverse else p,product)
    def reciprocal_shift():
        # Coefficient0 is implicitly one and never accessed by the reciprocal
        # emitter. Coefficient1 remains zero throughout that computation.
        if getattr(math,'virtual_zero',False):
            zero=()
            math.known_zero.add(tuple(zero))
            math.inverse([A[0],zero,*T])
            math.known_zero.remove(tuple(zero))
        else:
            with m.opened(E,'mobius_zero',12) as zero:
                math.known_zero.add(tuple(zero))
                math.inverse([A[0],zero,*T])
                math.known_zero.remove(tuple(zero))
    if inverse:
        math.triangular(A,1,T,True)
        math.triangular(D,1,T)
        reciprocal_shift()
        scale(True)
        math.triangular(D,1,T,True)
    else:
        math.triangular(D,1,T)
        scale(False)
        reciprocal_shift()
        math.triangular(D,1,T,True)
        math.triangular(A,1,T)






