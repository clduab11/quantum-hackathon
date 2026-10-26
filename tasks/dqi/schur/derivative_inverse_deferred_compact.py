# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Defer companion scalar measurements until the matching inverse transform."""
import argparse,json
from pathlib import Path
import kickmix as km
from .extension_inverse import Adapter,setup
from .cubic_low_workspace_inverse_compact import bind
from .fast_dqi import FastBuilder
from .lean_emitter import create as lean_create
from .inverse_ratio_mask_phase import apply as ratio_phase
from . import derivative_inverse_raw as raw
from . import bezout_payload_monic as monic
from . import bezout_payload_batched as batched
def build(n,inverse=False):
 m=setup()[0];m.inv_word=bind(m);b=FastBuilder(km.CircuitBuilder());aa=[b.create_quantum_register(12,f'A{i}') for i in range(n)];bb=[b.create_quantum_register(12,f'B{i}') for i in range(n)];ghost=b.create_classical_register(12*(n-1),'companion_ghost');ab=Adapter(b);sc,E=lean_create(m,ab)
 def companion(m,E,f,payloads,flag,inverse=False,one=False):
  size=len(payloads[0]);offset=0 if one else 24*(n//2-size+1);slots=[ghost[offset+12*j:offset+12*(j+1)] for j in range(2)]
  def rotate(back=False):
   for y in payloads:
    for i in (range(size-1) if back else reversed(range(size-1))):
     for q,r in zip(y[i],y[i+1]):b.cswap(km.q(flag),km.q(q),km.q(r))
  if not inverse:rotate()
  source=f[0] if inverse else ([] if one else f[-1])
  from contextlib import nullcontext
  with (m.inv_word(E,source) if source else nullcontext(None)) as si:
   for y,held in zip(payloads,slots):
    masked=E.A.open('deferred_companion_mask',12)
    if True:
     E.mac([('P',(flag,),0,(q,),0,(r,)) for q,r in zip(y[0],masked)])
     if si is not None:
      with m.opened(E,'deferred_companion_scale',12) as tmp:m.mon_slot(E,masked,si,source,tmp)
     if inverse:
      for q,bit in zip(masked,held):ab.z(q,bit)
      b.bit_store(held,False)
     rt=[];m.bil_terms(rt,m.KT,m.spec_plain(masked),m.spec_plain(f[0]) if one else [a^c for a,c in zip(m.spec_plain(f[0]),m.spec_plain(f[-1]))],y[0]);E.mac(rt)
     if one:
      for q,r in zip(masked,y[0]):E.cx(q,r)
     for i in range(1,size):E.mac(m.prod_rt(y[i],masked,f[i]))
     if inverse:
      fresh=b.alloc_bits(12);b.hmr(km.array([km.q(q) for q in masked]),fresh);E.A.close('deferred_companion_mask',masked)
      if one:
       for q,bit in zip(y[0],fresh):b.push_condition(bit);b.cz(km.q(flag),km.q(q));b.pop_condition()
      else:ratio_phase(b,f[-1],y[0],flag,fresh)
      b.bit_store(fresh,False);b.free(fresh)
     else:
      b.hmr(km.array([km.q(q) for q in masked]),held);E.A.close('deferred_companion_mask',masked)
  if inverse:rotate(True)
 oldm,oldb=monic.companion,batched.companion
 try:
  monic.companion=lambda m,E,f,payloads,flag,inverse=False:companion(m,E,f,payloads,flag,inverse,True)
  batched.companion=companion
  raw.apply(m,E,[[q.id for q in w] for w in aa],[[q.id for q in w] for w in bb],[],inverse)
 finally:monic.companion,batched.companion=oldm,oldb
 ab.release_recycle('deferred_emitter',sc);c=b.finish_circuit();held={bit.id for bit in ghost};return km.Circuit(str(c)+'\n'+''.join(f'BIT_STORE0 b{i}\n' for i in range(c.num_bits) if i not in held))


