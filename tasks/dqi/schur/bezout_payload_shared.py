# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Share both companion normalization inverses across the two payloads."""
from contextlib import contextmanager
from .bezout_payload_repair import divide
from .bezout_payload_repair import apply as original_apply
from . import bezout_payload_repair as base
import kickmix as km


def companion(m,E,f,payloads,flag,inverse=False):
 b=E.b.raw;size=len(payloads[0])
 def rotate(back=False):
  for y in payloads:
   for i in (range(size-1) if back else reversed(range(size-1))):
    for q,r in zip(y[i],y[i+1]):b.cswap(km.q(flag),km.q(q),km.q(r))
 if not inverse:rotate()
 source=f[0] if inverse else f[-1];eraser=f[-1] if inverse else f[0]
 with m.inv_word(E,source) as si,m.inv_word(E,eraser) as ei:
  for y in payloads:
   with m.opened(E,'bez_companion_mask',12) as masked:
    E.mac([('P',(flag,),0,(q,),0,(r,)) for q,r in zip(y[0],masked)])
    with m.opened(E,'bez_companion_scale',12) as tmp:m.mon_slot(E,masked,si,source,tmp)
    rt=[];m.bil_terms(rt,m.KT,m.spec_plain(masked),[a^c for a,c in zip(m.spec_plain(f[0]),m.spec_plain(f[-1]))],y[0]);E.mac(rt)
    for i in range(1,size):E.mac(m.prod_rt(y[i],masked,f[i]))
    with m.opened(E,'bez_companion_recover',12) as original:
     rr=m.prod_rt(original,y[0],ei);E.mac(rr);E.free([('P',(flag,),0,(q,),0,(r,)) for q,r in zip(original,masked)]);E.free(rr)
 if inverse:rotate(True)


def apply(*args,**kwargs):
 old=base.companion
 try:
  base.companion=companion
  return original_apply(*args,**kwargs)
 finally:base.companion=old
