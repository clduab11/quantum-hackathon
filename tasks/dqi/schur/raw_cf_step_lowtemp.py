# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Unnormalized continued-fraction fold N <- (a+b*x)N+q*B, B <- N.

Two consumed heads provide the two added polynomial coefficients. This first
implementation uses two transient output fields and deferred head phases.
"""
from contextlib import contextmanager
import argparse,json
from pathlib import Path
import numpy as np
import kickmix as km
from .extension_inverse import Adapter,setup
from .fast_dqi import FastBuilder
from .lean_emitter import create as lean_create
from .schur_gap_fold import quadratic
from .triangular_dp import DPArithmetic
from .schur_fold import axpy
from .schur_division_lowtemp import create as quotient


@contextmanager
def evaluate(b,N,B,kappa):
 m=setup()[0];power=[(1,0),(0,1)]
 for i in range(2,max(len(N),len(B))):
  a,c=power[-1];power.append((m.gmul(kappa,c),a^c))
 def apply():
  for bank in [N,B]:
   for i in range(2,len(bank)):
    axpy(b,bank[i],bank[0],power[i][0],m);axpy(b,bank[i],bank[1],power[i][1],m)
 apply();yield [q.id for w in N[:2] for q in w],[q.id for w in B[:2] for q in w];apply()


def build(size,kappa,inverse=False):
 assert size>=2;m=setup()[0];b=FastBuilder(km.CircuitBuilder());a=b.create_quantum_register(12,'a');h=b.create_quantum_register(12,'b');N=[b.create_quantum_register(12,f'N{i}') for i in range(size)];B=[b.create_quantum_register(12,f'B{i}') for i in range(size-1)];high=[b.create_quantum_register(12,f'Bt{i}') for i in range(2)];ghost=b.create_classical_register(24,'head_ghost');ab=Adapter(b);sc,E=lean_create(m,ab);dest=B+high;math=DPArithmetic(m,E);pts,I=m.vinv(size+1)
 def update():
  for col,x in enumerate(pts):
   left=math.spec([(1,[q.id for q in a],1),(x,[q.id for q in h],1)]);right=math.spec([(m.gpow(x,i),[q.id for q in w],1) for i,w in enumerate(N)])
   def targets(tb):return [dest[i][k].id for i in range(size+1) for k in m.bitlist(m.gmul(I[i][col],m.tmask(tb)),12)]
   math.product(left,right,targets)
 if inverse:
  with evaluate(b,dest,N,kappa) as (nv,dv):quotient(b,E,nv,dv,[q.id for q in list(a)+list(h)],kappa,[])
  for q,bit in zip(list(a)+list(h),ghost):ab.z(q.id,bit)
  b.bit_store(ghost,False);update();quadratic(b,dest,kappa,True)
 else:
  b.bit_store(ghost,False);quadratic(b,dest,kappa);update();b.hmr(km.array(list(a)+list(h)),ghost)
 ab.release_recycle('raw_cf_step_emitter',sc);c=b.finish_circuit();return km.Circuit(str(c)+'\n'+''.join(f'BIT_STORE0 b{i}\n' for i in range(24,c.num_bits)))


