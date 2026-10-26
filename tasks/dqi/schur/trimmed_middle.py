# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Trim zero rows/columns before emitting a bounded middle product.

The round-4 emitter already drops known-zero coefficients, but its choice
between evaluation and schoolbook uses the untrimmed rectangle. This changes
only that bilinear algorithm choice; it allocates no additional qubits.
"""
from .mobius_series import BoundedArithmetic

class TrimmedArithmetic(BoundedArithmetic):
    def sparse_middle(self,A,q,low,high):
        return self.offset_middle(A,q,low,high,0)

    def offset_middle(self,A,q,low,high,offset):
        """high[i] += sum_j A^q[len(low)+offset+i-j] low[j]."""
        nonzero=[j for j in range(1,len(A)) if tuple(A[j]) not in self.known_zero]
        if not nonzero:return
        degree=q*max(nonzero)
        width=degree-offset
        if width<=0:return
        lo=low[-min(len(low),width):]
        hi=high[:min(len(high),width)]
        if not lo or not hi:return
        n=len(lo)+len(hi)-1;m=self.m
        pairs=[(i,j,(len(lo)+offset+i-j)//q)
               for i in range(len(hi)) for j in range(len(lo))
               if (len(lo)+offset+i-j)%q==0
               and (len(lo)+offset+i-j)//q in nonzero]
        if len(pairs)<=n:
            for i,j,h in pairs:
                self.product(self.spec([(1,A[h],q)]),self.spec([(1,lo[j],1)]),lambda tb,i=i:[hi[i][b] for b in tb])
            return
        pts,I=m.vinv(n)
        for a,point in enumerate(pts):
            left=self.spec([(I[j-1][a],A[(j+offset)//q],q)
                            for j in range(1,n+1)
                            if (j+offset)%q==0 and (j+offset)//q in nonzero])
            if not any(left):continue
            right=self.spec([(m.gpow(point,j),word,1) for j,word in enumerate(reversed(lo))])
            powers=[m.gpow(point,i) for i in range(len(hi))]
            def targets(tb):
                return [hi[i][k] for i,power in enumerate(powers)
                        for k in m.bitlist(m.gmul(power,m.tmask(tb)),12)]
            self.product(left,right,targets)

    def triangular_suffix(self,A,q,target,start,inverse=False):
        if len(target)<=1 or start>=len(target):return
        if start<=0:return self.triangular(A,q,target,inverse)
        cut=len(target)//2;lo,hi=target[:cut],target[cut:]
        def middle():
            skip=max(0,start-cut)
            self.offset_middle(A,q,lo,hi[skip:],skip)
        if inverse:
            self.triangular_suffix(A,q,lo,start,True);middle()
            self.triangular_suffix(A,q,hi,max(0,start-cut),True)
        else:
            self.triangular_suffix(A,q,hi,max(0,start-cut));middle()
            self.triangular_suffix(A,q,lo,start)
