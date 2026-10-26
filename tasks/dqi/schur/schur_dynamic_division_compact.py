# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Extension division for a coherently selected quadratic node polynomial."""
from contextlib import contextmanager
import kickmix as km
from .extension_inverse import setup,extension_norm_rt,classical_transpose
from .schur_control import caxpy_rt
from .low_workspace_inverse import bind
from .tower_inverse import map_ops,apply_map
from .recursive_forney import inverse_dot_data


def norm_rt(m,den,target,kappa,controls):
 rt=extension_norm_rt(m,den,target,kappa)
 for flag,delta in controls:
  for i,q in enumerate(den[12:]):
   v=m.gmul(delta,m.gmul(1<<i,1<<i));rt.append(('P',(flag,),0,(q,),0,tuple(target[j] for j in range(12) if v>>j&1)))
 return rt


@contextmanager
def numerator(b,E,num,den,out,kappa,controls,keep=False,erase=False):
 m=setup()[0];n0,n1=num[:12],num[12:];d0,d1=den[:12],den[12:]
 with m.opened(E,'dynamic_division_q',12) as q:
  qr=m.prod_rt(q,n1,d1);E.mac(qr);rt=[]
  m.bil_terms(rt,m.KT,m.spec_plain(n0),[a^c for a,c in zip(m.spec_plain(d0),m.spec_plain(d1))],tws_of=lambda js:[out[j] for j in js]+[out[12+j] for j in js])
  m.bil_terms(rt,m.KT,[a^c for a,c in zip(m.spec_plain(n0),m.spec_plain(n1))],m.spec_plain(d0),tws_of=lambda js:[out[12+j] for j in js])
  for i,v in enumerate(q):
   c=m.gmul(kappa,1<<i);rt.append(('L',(v,),0,tuple(out[j] for j in range(12) if c>>j&1)))
  for flag,delta in controls:rt+=caxpy_rt(m,flag,q,out[:12],delta)
  if erase:E.free(rt)
  else:E.mac(rt)
  yield
  if not (keep or erase):E.free(rt)
  E.free(qr)


def create(b,E,num,den,out,kappa,controls):
 m=setup()[0];m.inv_word=bind(m)
 with m.opened(E,'dynamic_division_norm',12) as nn:
  nr=norm_rt(m,den,nn,kappa,controls);E.mac(nr)
  with numerator(b,E,num,den,out,kappa,controls,keep=True):pass
  with m.inv_word(E,nn) as ni,m.opened(E,'dynamic_division_scale',12) as temp:
   m.mon_slot(E,out[:12],ni,nn,temp);m.mon_slot(E,out[12:],ni,nn,temp)
  E.free(nr)


def phase(b,E,num,den,mask,kappa,controls):
 m,_,fw,bk,tr=setup()
 with m.opened(E,'dynamic_division_phase_norm',12) as nn,m.opened(E,'dynamic_division_phase_numerator',24) as pp:
  nr=norm_rt(m,den,nn,kappa,controls);E.mac(nr)
  with numerator(b,E,num,den,pp,kappa,controls,keep=True):pass
  if True:
   ns=km.array([km.q(i) for i in nn]);ps=km.array([km.q(i) for i in pp]);bops=map_ops(bk);trans=tuple(sum(((fw[i]>>j)&1)<<i for i in range(12)) for j in range(12));mops=map_ops(trans)
   for word in [ns,ps[:12],ps[12:]]:apply_map(b,word,bops)
   for word in [mask[:12],mask[12:]]:apply_map(b,word,mops)
   u=b.alloc_qubits(12)
   def umap():
    classical_transpose(b,ps[:12],mask[:12],u);classical_transpose(b,ps[12:],mask[12:],u)
   umap();leaf,inv,cleanup=inverse_dot_data(b,ns,u);b.cz(leaf,inv);cleanup();umap();b.free(u)
   for word in [mask[:12],mask[12:]]:apply_map(b,word,mops,True)
   for word in [ns,ps[:12],ps[12:]]:apply_map(b,word,bops,True)
  with numerator(b,E,num,den,pp,kappa,controls,erase=True):pass
  E.free(nr)
