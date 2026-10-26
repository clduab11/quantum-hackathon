# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Reversible conversion of a consumed extension sample to a Schur pivot."""
import json
from pathlib import Path
import numpy as np
import kickmix as km
from .extension_inverse import Adapter,setup
from .low_workspace_inverse import bind
from .base_inverse import inplace as invert12
from .tower_inverse import map_ops,apply_map
from .fast_dqi import FastBuilder


def build(node,inverse=False,first=False):
 m,k,fw,bk,tr=setup();m.inv_word=bind(m);b=FastBuilder(km.CircuitBuilder())
 lo=b.create_quantum_register(12,'a');hi=b.create_quantum_register(12,'b');g=b.create_quantum_register(12,'g')
 prev_a=b.create_quantum_register(12,'prev_a');prev_b=b.create_quantum_register(12,'prev_b')
 ab=Adapter(b);scratch=ab.qubits(3);E=m.Em(ab,*scratch,m.Alloc(ab));A=[q.id for q in lo];B=[q.id for q in hi];G=[q.id for q in g]
 def axpy(src,dst,c):
  for i,q in enumerate(src):
   value=m.gmul(c,1<<i)
   for j in range(12):
    if value>>j&1:b.cx(q,dst[j])
 def gupdate():
  invert12(b,g)
  with m.eq_test(E,B,0) as z:
   E.cx(z,B[0]);ops=map_ops([m.gpow(1<<i,2) for i in range(12)]);apply_map(b,hi,ops)
   with m.inv_word(E,B) as bi,m.opened(E,'pivot_scale_g',12) as temp:m.mon_slot(E,G,B,bi,temp)
   apply_map(b,hi,ops,True);E.cx(z,B[0])
 def offset():
  if not first:b.cx(prev_a,lo);b.cx(prev_b,lo);b.cx(prev_b,hi)
 def scale(back=False):
  with m.inv_word(E,G) as gi,m.opened(E,'pivot_scale_values',12) as temp:
   for word in [A,B]:m.mon_slot(E,word,gi if back else G,G if back else gi,temp)
 if inverse:
  gupdate();offset();scale(True);axpy(hi,lo,node)
 else:
  axpy(hi,lo,node);scale();offset();gupdate()
 ab.release_recycle('pivot_emitter',scratch);c=b.finish_circuit()
 return km.Circuit(str(c)+'\n'+''.join(f'BIT_STORE0 b{i}\n' for i in range(c.num_bits)))

