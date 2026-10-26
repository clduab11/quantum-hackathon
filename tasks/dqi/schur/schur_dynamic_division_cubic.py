# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Extension quotient using its zero low output as the norm workspace."""
import kickmix as km
from .extension_inverse import setup
from .cubic_low_workspace_inverse import bind
from .schur_dynamic_division_compact import norm_rt
from .schur_control import caxpy


def create(b,E,num,den,out,kappa,controls):
 m=setup()[0];m.inv_word=bind(m);n0,n1=num[:12],num[12:];d0,d1=den[:12],den[12:];u,t=out[:12],out[12:]
 nr=norm_rt(m,den,u,kappa,controls);E.mac(nr)
 E.mac(m.prod_rt(t,n0,d1));E.mac(m.prod_rt(t,n1,d0))
 with m.inv_word(E,u) as ni,m.opened(E,'sequential_norm_scale',12) as tmp:m.mon_slot(E,t,ni,u,tmp)
 E.free(nr)
 flag=b.alloc_qubits(1)[0].id
 with m.eq_test(E,d1,0) as z:E.cx(z,flag)
 def swap():
  for a,c in [(n0,n1),(d0,d1)]:
   for q,r in zip(a,c):b.cswap(km.q(flag),km.q(q),km.q(r))
 swap()
 for q,r in zip(n1,u):E.cx(q,r)
 E.mac(m.prod_rt(u,t,d0))
 with m.eq_test(E,d1,0) as z:caxpy(m,E,z,n1,u,1)
 with m.inv_word(E,d1) as di,m.opened(E,'sequential_low_scale',12) as tmp:m.mon_slot(E,u,di,d1,tmp)
 for q,r in zip(t,u):E.cx(q,r)
 caxpy(m,E,flag,t,u,1)
 swap()
 with m.eq_test(E,d1,0) as z:E.cx(z,flag)
 b.free(km.array([km.q(flag)]))
