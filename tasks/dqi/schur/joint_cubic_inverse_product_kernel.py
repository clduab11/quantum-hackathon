# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""A jointly synthesized quadratic norm/subtrace front end for cubic inversion.

The frozen depth-one XOR/AND cover is checked against all256 inputs before
use. Only this front end differs from the checked cubic trace kernel.
"""
import inspect,json
from functools import lru_cache
from pathlib import Path
import kickmix as km
from . import cubic_inverse_product_kernel as base
from .cubic_trace_field import data
from .tower_inverse import linear_xor


@lru_cache(None)
def joint_data():
 # Deterministic replacement for the absent upstream 16-AND parameter file.
 from .crt_multiplier import small_terms
 from .cubic_trace_field import cube_terms
 g=km.GF2Field(4);k=data()['kappa'];kk=g.mul(k,k)
 cubes,linear,_=cube_terms()
 terms=[(a,b<<4,g.mul(k,o)) for a,b,o in small_terms(g.modulus)]
 terms += [(a,b,g.mul(k,o)<<4) for a,b,o in cubes]
 terms += [(a<<4,b<<4,g.mul(kk,o)<<4) for a,b,o in cubes]
 cols=[g.mul(k,v)<<4 for v in linear]+[g.mul(kk,v)<<4 for v in linear]
 assert len(terms)==17
 def want(x):
  b,c=x&15,x>>4;return g.mul(k,g.mul(b,c))|((g.mul(k,g.pow(b,3))^g.mul(kk,g.pow(c,3)))<<4)
 for x in range(256):
  v=0
  for j,col in enumerate(cols):
   if x>>j&1:v^=col
  for a,b,o in terms:
   if (a&x).bit_count()%2 and (b&x).bit_count()%2:v^=o
  assert v==want(x),(x,v,want(x))
 return tuple(tuple(t) for t in terms),tuple(cols)


def load_joint(b,left,right,Q,N):
 source=km.array([*left,*right]);target=km.array([*Q,*N]);terms,cols=joint_data();base.xor_terms(b,source,source,target,terms);linear_xor(b,source,target,cols)


source=inspect.getsource(base.trace_inverse)
old=""" xor_terms(b,bb,c,Q,qterms);linear_xor(b,a,Q,[g.mul(1<<j,1<<j) for j in range(4)])
 xor_terms(b,a,Q,N,terms)
 for word,scale in [(bb,k),(c,g.mul(k,k))]:
  xor_terms(b,word,word,N,[(lm,rm,g.mul(scale,om)) for lm,rm,om in cterms]);linear_xor(b,word,N,[g.mul(scale,v) for v in lc])"""
new=""" load_joint(b,bb,c,Q,N);linear_xor(b,a,Q,[g.mul(1<<j,1<<j) for j in range(4)])
 xor_terms(b,a,Q,N,terms)"""
assert source.count(old)==1
ns=dict(base.__dict__);ns['load_joint']=load_joint;exec(source.replace(old,new),ns);trace_inverse=ns['trace_inverse'];exec(inspect.getsource(base.apply),ns);apply=ns['apply']
