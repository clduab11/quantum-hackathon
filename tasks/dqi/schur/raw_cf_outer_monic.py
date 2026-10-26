# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Contract the proper outer rational tail without storing its two zero tops."""
import argparse,json
from pathlib import Path
import numpy as np
import kickmix as km
from .extension_inverse import Adapter,setup
from .cubic_low_workspace_inverse_compact import bind
from .fast_dqi import FastBuilder
from .lean_emitter import create
from .triangular_dp import DPArithmetic
from .schur_division_lowtemp import create as quotient
from .raw_cf_step import evaluate
from .tower_inverse import map_ops,apply_map
from .schur_fold import axpy


def build(n,kappa,inverse=False):
 m=setup()[0];m.inv_word=bind(m);b=FastBuilder(km.CircuitBuilder());N=[b.create_quantum_register(12,f'N{i}') for i in range(n+1)];B=[b.create_quantum_register(12,f'B{i}') for i in range(n)];ghost=b.create_classical_register(24,'outer_ghost');ab=Adapter(b);sc,E=create(m,ab);a=E.A.open('outer_a',12);h=E.A.open('outer_b',12);math=DPArithmetic(m,E);pts,I=m.vinv(n+2)
 def qscale(back=False):
  ops=map_ops([m.gmul(kappa,1<<j) for j in range(12)])
  for i in (range(n) if back else reversed(range(n))):
   if not back:apply_map(b,B[i],ops)
   for j in [i-1,i-2]:
    if j>=0:b.cx(B[j],B[i])
   if back:apply_map(b,B[i],ops,True)
 def update():
  for col,x in enumerate(pts):
   left=math.spec([(1,a,1),(x,h,1)]);right=math.spec([(m.gpow(x,i),[q.id for q in w],1) for i,w in enumerate(N)])
   def targets(tb):return [B[i][k].id for i in range(n) for k in m.bitlist(m.gmul(I[i][col],m.tmask(tb)),12)]
   math.product(left,right,targets)
 if inverse:
  with evaluate(b,B,N,kappa) as (nv,dv):quotient(b,E,nv,dv,a+h,kappa,[])
  for q,bit in zip(a+h,ghost):ab.z(q,bit)
  b.bit_store(ghost,False);update();qscale(True)
 else:
  b.cx(B[-1],km.array([km.q(q) for q in h]))
  b.cx(B[-2],km.array([km.q(q) for q in a]));b.cx(B[-1],km.array([km.q(q) for q in a]))
  E.mac(m.prod_rt(a,h,[q.id for q in N[-2]]))
  qscale();update();b.hmr(km.array([km.q(q) for q in a+h]),ghost)
 if inverse:
  b.cx(B[-2],km.array([km.q(q) for q in a]));b.cx(B[-1],km.array([km.q(q) for q in a]))
  E.free(m.prod_rt(a,h,[q.id for q in N[-2]]))
  b.cx(B[-1],km.array([km.q(q) for q in h]))
 E.A.close('outer_b',h);E.A.close('outer_a',a);ab.release_recycle('outer_emitter',sc);c=b.finish_circuit();return km.Circuit(str(c)+'\n'+''.join(f'BIT_STORE0 b{i}\n' for i in range(24,c.num_bits)))


