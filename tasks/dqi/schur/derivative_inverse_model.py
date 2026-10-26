# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Exact half-degree Bezout factorization of division by B' modulo B.

Only an algebra model and counted field operations. No quantum implementation
or score is claimed; coherent Euclidean gaps and padding remain separate work.
"""
import json,random,time
from pathlib import Path
from .quadratic_schur_model import F


def trim(a):
 a=list(a)
 while a and not a[-1]:a.pop()
 return a

def divide(f,g):
 f=trim(f);g=trim(g);assert g;q=[0]*max(0,len(f)-len(g)+1);iv=F.inv(g[-1])
 for i in reversed(range(len(q))):
  v=F.mul(f[len(g)-1+i],iv);q[i]=v
  for j,c in enumerate(g):f[i+j]^=F.mul(v,c)
 return trim(q),trim(f)


def invmod(a,b):
 f,g=trim(b),trim(a);x,y=[],[1]
 while g:
  q,r=divide(f,g);f,g=g,r;x,y=y,F.add(x,F.product(q,y))
 assert len(f)==1
 return divide(F.scale(x,F.inv(f[0])),b)[1]


def solve(A,b):
 n=len(A);a=[list(row)+[v] for row,v in zip(A,b)]
 for j in range(n):
  i=next(i for i in range(j,n) if a[i][j]);a[i],a[j]=a[j],a[i];iv=F.inv(a[j][j]);a[j]=[F.mul(v,iv) for v in a[j]]
  for i in range(n):
   if i!=j and a[i][j]:
    v=a[i][j];a[i]=[x^F.mul(v,y) for x,y in zip(a[i],a[j])]
 return [row[-1] for row in a]


def bezout(f,g):
 n=max(len(f),len(g))-1;f=list(f)+[0]*(n+1-len(f));g=list(g)+[0]*(n+1-len(g));num=[[F.mul(f[i],g[j])^F.mul(g[i],f[j]) for j in range(n+1)] for i in range(n+1)];out=[[0]*n for _ in range(n)]
 for i in reversed(range(1,n+1)):
  for j in range(n):
   v=num[i][j];out[i-1][j]^=v;num[i][j]^=v;num[i-1][j+1]^=v
 assert not any(v for row in num for v in row)
 return out


def matvec(A,b):
 return [xor(F.mul(x,y) for x,y in zip(row,b)) for row in A]


def xor(values):
 out=0
 for v in values:out^=v
 return out


def bezout_inverse(f,g,payload,stats):
 """Arbitrary exact Euclidean degree gaps, via the quotient Hankel block."""
 f,g=trim(f),trim(g);m,n=len(f)-1,len(g)-1
 assert m>=n>=0 and len(payload)==m
 if m==n:
  _,r=divide(f,g);return bezout_inverse(g,r,payload,stats)
 h=m-n;stats['blocks']+=1;stats['max_gap']=max(stats['max_gap'],h);stats['rank_one_blocks']+=h==1
 if not n:
  # g constant: Bez(f,g) is g times the anti-triangular Hankel of f.
  H=[[F.mul(g[0],f[i+j+1]) if i+j+1<=m else 0 for j in range(m)] for i in range(m)];return solve(H,payload)
 q,r=divide(f,g);assert r;gl=F.inv(g[-1]);z=list(payload);high=z[n:]
 # Solve G_high*high = input_high, where columns are x^j*g.
 for i in reversed(range(h)):
  for j in range(i+1,h):
   if 0<=n+i-j<len(g):high[i]^=F.mul(g[n+i-j],high[j]);stats['field_products']+=1
  high[i]=F.mul(high[i],gl);stats['field_products']+=1
 low=z[:n]
 for i in range(n):
  for j,v in enumerate(high):
   if 0<=i-j<len(g):low[i]^=F.mul(g[i-j],v);stats['field_products']+=1
 low=bezout_inverse(g,r,low,stats);H=[[q[i+j+1] if i+j+1<len(q) else 0 for j in range(h)] for i in range(h)];high=solve(H,high)
 for j in range(h):
  for i,v in enumerate(low):
   if 0<=i-j<len(g):high[j]^=F.mul(g[i-j],v);stats['field_products']+=1
 # Solve transpose(G_high)*output_high = high.
 for i in range(h):
  for j in range(i):
   if 0<=n+j-i<len(g):high[i]^=F.mul(g[n+j-i],high[j]);stats['field_products']+=1
  high[i]=F.mul(high[i],gl);stats['field_products']+=1
 return low+high


def derivative_inverse(A,B):
 n=len(B)-1;assert n%2 and B[-1]==1 and len(A)==n;t=n//2;root=lambda v:F.pow(v,2048);E=[root(v) for v in B[::2]];O=[root(v) for v in B[1::2]];r=[root(v) for v in A];even=r[::2];odd=r[1::2];lead=even[-1];low=[x^F.mul(c,lead) for x,c in zip(even[:-1],O[:-1])];stats=dict(field_products=2*t,blocks=0,max_gap=0,rank_one_blocks=0);left=bezout_inverse(E,O,low,stats);right=bezout_inverse(E,O,odd,stats);out=[0]*n
 for i,v in enumerate(right):out[2*i]=v
 for i,v in enumerate(left):out[2*i+1]=v
 out[-1]=lead^xor(F.mul(c,v) for c,v in zip(O[:-1],right));out=[F.mul(v,v) for v in out];H=[[B[i+j+1] if i+j+1<len(B) else 0 for j in range(n)] for i in range(n)];return matvec(H,out),stats


