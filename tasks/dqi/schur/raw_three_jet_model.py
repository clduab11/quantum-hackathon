# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Three-field infinity jet with a tail gauge making the final B monic."""
import json,random
from pathlib import Path
from .raw_cf_model import extract
from .quadratic_schur_model import F,node_maps
from .derivative_inverse_model import trim


def endpoint(heads):
 p=d=0;q=1
 for a,b in heads:p,q,d=q,p^F.mul(b,q),d^F.mul(p,q)^F.mul(a^b,F.mul(q,q))
 if q:return [F.mul(d,F.inv(q)),p],[q],None,(p,q,d)
 if not d:return [p],[],None,(p,q,d)
 return [],[],'infinite_simple_pole',(p,q,d)


def synthesize(heads):
 A,B,e,j=endpoint(heads)
 if e:return A,B,e,j
 _,kap,_,_=node_maps(len(heads))
 for i,(a,b) in reversed(list(enumerate(heads))):A,B=trim(F.add(F.product([a,b],A),F.product([kap[i],1,1],B))),A
 return A,B,None,j


