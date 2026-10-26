# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Monic proper outer inverse with a demolished remainder evaluation."""
import argparse,json
from pathlib import Path
import kickmix as km
from .extension_inverse import Adapter,setup
from .fast_dqi import FastBuilder
from .lean_emitter import create as emit
from .triangular_dp import DPArithmetic
from .raw_cf_outer_monic import build as old_build
from .raw_cf_step_destructive import evaluate
from .destructive_quotient import create as quotient
from .tower_inverse import map_ops,apply_map
from .schur_fold import axpy


def build(n,kappa,inverse=False):
 if not inverse:return old_build(n,kappa)
 m=setup()[0];b=FastBuilder(km.CircuitBuilder());N=[b.create_quantum_register(12,f'N{i}') for i in range(n+1)];B=[b.create_quantum_register(12,f'B{i}') for i in range(n)];ghost=b.create_classical_register(24,'outer_ghost');ab=Adapter(b);sc,E=emit(m,ab);a=E.A.open('destroy_outer_a',12);h=E.A.open('destroy_outer_b',12);math=DPArithmetic(m,E)
 evaluate(b,B,kappa);evaluate(b,N,kappa);quotient(b,E,[q.id for w in B[:2] for q in w],[q.id for w in N[:2] for q in w],a+h,kappa)
 for q,bit in zip(a+h,ghost):ab.z(q,bit)
 b.bit_store(ghost,False);evaluate(b,N,kappa)
 if n<=4:
  for i in range(2,n):E.mac(m.prod_rt([q.id for q in B[i]],a,[q.id for q in N[i]])+m.prod_rt([q.id for q in B[i]],h,[q.id for q in N[i-1]]))
 else:
  pts,I=m.vinv(n)
  for col,x in enumerate(pts):
   left=math.spec([(1,a,1),(x,h,1)]);right=math.spec([(m.gpow(x,i),[q.id for q in w],1) for i,w in enumerate(N[1:n])])
   def targets(tb):return [B[i][j].id for i in range(2,n) for j in m.bitlist(m.gmul(I[i-1][col],m.tmask(tb)),12)]
   math.product(left,right,targets)
 # The absent top two coefficients of l*N contribute to the remainder.
 power=[(1,0),(0,1)]
 for i in range(2,n+2):
  u,v=power[-1];power.append((m.gmul(kappa,v),u^v))
 for j in range(2):
  axpy(b,km.array([km.q(q) for q in a]),B[j],power[n][j],m);axpy(b,km.array([km.q(q) for q in h]),B[j],power[n+1][j],m)
 rt=[]
 def correction(js):
  value=sum(1<<j for j in js);return [B[i][j].id for i in range(2) for j in m.bitlist(m.gmul(power[n][i],value),12)]
 m.bil_terms(rt,m.KT,m.spec_plain(h),m.spec_plain([q.id for q in N[-2]]),tws_of=correction);E.mac(rt)
 evaluate(b,B,kappa)
 ops=map_ops([m.gmul(kappa,1<<j) for j in range(12)])
 for i in range(n):
  for j in [i-1,i-2]:
   if j>=0:b.cx(B[j],B[i])
  apply_map(b,B[i],ops,True)
 # Recovered heads still follow the simple monic leading-coefficient formulas.
 b.cx(B[-2],km.array([km.q(q) for q in a]));b.cx(B[-1],km.array([km.q(q) for q in a]));E.free(m.prod_rt(a,h,[q.id for q in N[-2]]));b.cx(B[-1],km.array([km.q(q) for q in h]));E.A.close('destroy_outer_b',h);E.A.close('destroy_outer_a',a);ab.release_recycle('destroy_outer_emitter',sc);c=b.finish_circuit();return km.Circuit(str(c)+'\n'+''.join(f'BIT_STORE0 b{i}\n' for i in range(24,c.num_bits)))
