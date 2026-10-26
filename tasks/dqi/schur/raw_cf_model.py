# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Raw quadratic-node continued fraction with a projective infinity jet.

No scalar normalization or node swapping is required in the head extraction.
The two leading terms at infinity determine a finite affine terminal tail;
a completed infinite terminal tail is represented projectively.
"""
import json,random,time
from pathlib import Path
from .quadratic_schur_model import F,node_maps,transform,bmul,einv
from .derivative_inverse_model import trim,divide


def extract(s):
 n=len(s)//2;nodes,kap,P,maps=node_maps(n);v=transform(s,maps);heads=[];ghost=[]
 for i in range(n):
  b=v[i]>>12;a=(v[i]&4095)^F.mul(nodes[i]&4095,b);heads.append((a,b))
  for j in range(i+1,n):
   den=v[j]^a^bmul(nodes[j],b);ghost.append(den);v[j]=bmul(einv(den),kap[i]^kap[j]) if den else 0
 return heads,ghost


def endpoint(heads):
 p0=p1=q1=0;q0=1
 for a,b in heads:
  p0,p1,q0,q1=q0,q0^q1,p0^F.mul(b,q0),p1^F.mul(b,q1)^F.mul(a,q0)
 if q0:
  qi=F.inv(q0);h=F.mul(p0,qi);k=F.mul(p1,qi)^F.mul(h,F.mul(q1,qi));return [k,h],[1],None,(p0,p1,q0,q1)
 if not q1:return [1],[],None,(p0,p1,q0,q1)
 return [],[],'infinite_simple_pole',(p0,p1,q0,q1)


def synthesize(heads):
 N,B,exc,jet=endpoint(heads)
 if exc:return N,B,exc,jet
 _,kap,_,_=node_maps(len(heads))
 for i,(a,b) in reversed(list(enumerate(heads))):N,B=trim(F.add(F.product([a,b],N),F.product([kap[i],1,1],B))),N
 if not B:return N,B,'zero_denominator',jet
 if len(N)>=len(B):return N,B,'improper_final',jet
 return N,B,None,jet


