# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Native quadratic-extension division creation and measured-output phase.

The extension polynomial is x^2+x+kappa. Norm/inverse contraction retains
only base-field scratch. Existing attributed multiplier/tower helpers emit
all arithmetic. These are component kernels, not complete DQI decoders.
"""
import json
from pathlib import Path
import numpy as np
import kickmix as km
from .extension_inverse import Adapter,setup,extension_norm_rt,classical_transpose
from .low_workspace_inverse import bind
from .tower_inverse import map_ops,apply_map
from .recursive_forney import inverse_dot_data
from .fast_dqi import FastBuilder


def numerator_rt(m,num,den,out,kappa):
 # num * conjugate(den), using three base-field multiplications.
 n0,n1=num[:12],num[12:];d0,d1=den[:12],den[12:]
 p=m.spec_plain(n0);q=m.spec_plain(n1);r=[a^b for a,b in zip(p,q)]
 s=m.spec_plain(d0);t=m.spec_plain(d1);u=[a^b for a,b in zip(s,t)]
 rt=[]
 m.bil_terms(rt,m.KT,p,u,tws_of=lambda js:[out[j] for j in js]+[out[12+j] for j in js])
 def ktargets(js):
  v=0
  for j in js:v^=m.gmul(kappa,1<<j)
  return [out[j] for j in range(12) if v>>j&1]
 m.bil_terms(rt,m.KT,q,t,tws_of=ktargets)
 m.bil_terms(rt,m.KT,r,s,tws_of=lambda js:[out[12+j] for j in js])
 return rt


def create(b,E,num,den,out,kappa):
 m=setup()[0];m.inv_word=bind(m)
 with m.opened(E,'division_norm',12) as nn,m.opened(E,'division_numerator',24) as pp:
  nr=extension_norm_rt(m,den,nn,kappa);pr=numerator_rt(m,num,den,pp,kappa)
  E.mac(nr);E.mac(pr)
  with m.inv_word(E,nn) as ni:
   E.mac(m.prod_rt(out[:12],pp[:12],ni));E.mac(m.prod_rt(out[12:],pp[12:],ni))
  E.free(pr);E.free(nr)


def phase(b,E,num,den,mask,kappa):
 m,_,fw,bk,tr=setup()
 with m.opened(E,'division_phase_norm',12) as nn,m.opened(E,'division_phase_numerator',24) as pp:
  nr=extension_norm_rt(m,den,nn,kappa);pr=numerator_rt(m,num,den,pp,kappa);E.mac(nr);E.mac(pr)
  ns=km.array([km.q(i) for i in nn]);ps=km.array([km.q(i) for i in pp]);bops=map_ops(bk)
  trans=tuple(sum(((fw[i]>>j)&1)<<i for i in range(12)) for j in range(12));mops=map_ops(trans)
  for word in [ns,ps[:12],ps[12:]]:apply_map(b,word,bops)
  for word in [mask[:12],mask[12:]]:apply_map(b,word,mops)
  u=b.alloc_qubits(12)
  def umap():
   classical_transpose(b,ps[:12],mask[:12],u);classical_transpose(b,ps[12:],mask[12:],u)
  umap();leaf,inv,cleanup=inverse_dot_data(b,ns,u);b.cz(leaf,inv);cleanup();umap();b.free(u)
  for word in [mask[:12],mask[12:]]:apply_map(b,word,mops,True)
  for word in [ns,ps[:12],ps[12:]]:apply_map(b,word,bops,True)
  E.free(pr);E.free(nr)


def build(phase_only=False):
 m,k,fw,bk,tr=setup();b=FastBuilder(km.CircuitBuilder());num=b.create_quantum_register(24,'num');den=b.create_quantum_register(24,'den')
 out=b.create_classical_register(24,'mask') if phase_only else b.create_quantum_register(24,'out')
 ab=Adapter(b);sc=ab.qubits(3);E=m.Em(ab,*sc,m.Alloc(ab))
 if phase_only:phase(b,E,[q.id for q in num],[q.id for q in den],out,k)
 else:create(b,E,[q.id for q in num],[q.id for q in den],[q.id for q in out],k)
 ab.release_recycle('division_emitter',sc);c=b.finish_circuit();public={v.id for v in out} if phase_only else set()
 return km.Circuit(str(c)+'\n'+''.join(f'BIT_STORE0 b{i}\n' for i in range(c.num_bits) if i not in public))


