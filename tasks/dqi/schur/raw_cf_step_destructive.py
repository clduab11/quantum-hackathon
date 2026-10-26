# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Consume the remainder evaluation before restoring the old polynomial."""
import argparse,json
from pathlib import Path
import kickmix as km
from .extension_inverse import Adapter,setup
from .fast_dqi import FastBuilder
from .lean_emitter import create as emit
from .triangular_dp import DPArithmetic
from .schur_gap_fold import quadratic
from .schur_fold import axpy
from .raw_cf_step_lowtemp import build as old_build
from .destructive_quotient import create as quotient


def evaluate(b,bank,kappa):
 m=setup()[0];power=[(1,0),(0,1)]
 for i in range(2,len(bank)):
  a,c=power[-1];power.append((m.gmul(kappa,c),a^c))
 for i in range(2,len(bank)):
  axpy(b,bank[i],bank[0],power[i][0],m);axpy(b,bank[i],bank[1],power[i][1],m)


def build(size,kappa,inverse=False):
 if not inverse:return old_build(size,kappa)
 m=setup()[0];b=FastBuilder(km.CircuitBuilder());a=b.create_quantum_register(12,'a');h=b.create_quantum_register(12,'b');N=[b.create_quantum_register(12,f'N{i}') for i in range(size)];B=[b.create_quantum_register(12,f'B{i}') for i in range(size-1)];high=[b.create_quantum_register(12,f'Bt{i}') for i in range(2)];ghost=b.create_classical_register(24,'head_ghost');ab=Adapter(b);sc,E=emit(m,ab);dest=B+high;math=DPArithmetic(m,E)
 evaluate(b,dest,kappa);evaluate(b,N,kappa);quotient(b,E,[q.id for w in dest[:2] for q in w],[q.id for w in N[:2] for q in w],[q.id for q in list(a)+list(h)],kappa)
 for q,bit in zip(list(a)+list(h),ghost):ab.z(q.id,bit)
 b.bit_store(ghost,False);evaluate(b,N,kappa)
 if size==2:E.mac(m.prod_rt([q.id for q in dest[2]],[q.id for q in h],[q.id for q in N[1]]))
 else:
  pts,I=m.vinv(size);source=list(reversed(N[1:]));target=list(reversed(dest[2:]))
  for col,x in enumerate(pts):
   left=math.spec([(1,[q.id for q in h],1),(x,[q.id for q in a],1)]);right=math.spec([(m.gpow(x,i),[q.id for q in w],1) for i,w in enumerate(source)])
   def targets(tb):return [target[i][j].id for i in range(size-1) for j in m.bitlist(m.gmul(I[i][col],m.tmask(tb)),12)]
   math.product(left,right,targets)
 evaluate(b,dest,kappa);quadratic(b,dest,kappa,True);ab.release_recycle('destroy_step_emitter',sc);c=b.finish_circuit();return km.Circuit(str(c)+'\n'+''.join(f'BIT_STORE0 b{i}\n' for i in range(24,c.num_bits)))
