# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Use a degree-one convolution for each two-term source division."""
from contextlib import contextmanager
from .bezout_payload_repair import divide as old_divide,apply as original_apply
from .bezout_payload_shared import companion
from . import bezout_payload_repair as base
from .triangular_dp import DPArithmetic


def divide(m,E,f,g,inverse=False,one=False,provided_inverse=None):
 n=len(g)-1;mm=len(f)-1
 if mm!=n+1 or n<4:return old_divide(m,E,f,g,inverse,one,provided_inverse)
 @contextmanager
 def inv():
  if one:yield None
  elif provided_inverse is not None:yield provided_inverse
  else:
   with m.inv_word(E,g[-1]) as gi:yield gi
 math=DPArithmetic(m,E);pts,I=m.vinv(n+1)
 def update():
  for a,point in enumerate(pts):
   left=math.spec([(1,f[n],1),(point,f[n+1],1)]);right=math.spec([(m.gpow(point,i),word,1) for i,word in enumerate(g[:-1])])
   def targets(tb):return [f[i][k] for i in range(n) for k in m.bitlist(m.gmul(I[i][a],m.tmask(tb)),12)]
   math.product(left,right,targets)
 with inv() as gi,m.opened(E,'bez_source_divide',12) as tmp:
  if inverse:
   update()
   if not one:m.mon_slot(E,f[n],g[-1],gi,tmp)
   E.mac(m.prod_rt(f[n],f[n+1],g[n-1]))
   if not one:m.mon_slot(E,f[n+1],g[-1],gi,tmp)
  else:
   if not one:m.mon_slot(E,f[n+1],gi,g[-1],tmp)
   E.mac(m.prod_rt(f[n],f[n+1],g[n-1]))
   if not one:m.mon_slot(E,f[n],gi,g[-1],tmp)
   update()


def apply(*args,**kwargs):
 oldcomp,olddiv=base.companion,base.divide
 try:
  base.companion=companion;base.divide=divide
  return original_apply(*args,**kwargs)
 finally:base.companion=oldcomp;base.divide=olddiv
