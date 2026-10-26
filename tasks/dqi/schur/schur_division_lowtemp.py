# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Extension quotient with output recycling and direct numerator-phase erasure.

Its low coordinate may be zero even for a nonzero copied numerator.  Erasure
uses the untouched numerator rather than multiplying by a nonexistent eraser.
"""
import kickmix as km
from .extension_inverse import setup
from .spooky_extension_norm_inverse import init_delayed
from .schur_dynamic_division_compact import norm_rt
from .schur_control import caxpy
from .cubic_mask_phase_compact import native_phase_inverse


def reciprocal(b,E,src):
 m=setup()[0];iv=init_delayed(m,E,src);mask=b.alloc_bits(12);b.hmr(km.array([km.q(q) for q in src]),mask)
 for q,r in zip(src,iv):E.b.swap(q,r)
 E.A.close('ext_delayed_inverse',iv);native_phase_inverse(b,src,mask);b.bit_store(mask,False);b.free(mask)


def create(b,E,num,den,out,kappa,controls):
 m=setup()[0];n0,n1=num[:12],num[12:];d0,d1=den[:12],den[12:];u,t=out[:12],out[12:];nr=norm_rt(m,den,u,kappa,controls);cr=m.prod_rt(t,n0,d1)+m.prod_rt(t,n1,d0);E.mac(nr);E.mac(cr);ni=init_delayed(m,E,u);norm_mask=b.alloc_bits(12);b.hmr(km.array([km.q(q) for q in u]),norm_mask);E.mac(m.prod_rt(u,t,ni));E.free(cr)
 for q,r in zip(u,t):E.b.swap(q,r)
 E.mac(nr)
 for q,bit in zip(u,norm_mask):E.b.z(q,bit)
 b.bit_store(norm_mask,False);b.free(norm_mask);mask=b.alloc_bits(12);b.hmr(km.array([km.q(q) for q in ni]),mask);E.A.close('ext_delayed_inverse',ni);native_phase_inverse(b,u,mask);b.bit_store(mask,False);b.free(mask);E.free(nr)
 flag=b.alloc_qubits(1)[0].id
 with m.eq_test(E,d1,0) as z:E.cx(z,flag)
 def swap():
  for left,right in [(n0,n1),(d0,d1)]:
   for q,r in zip(left,right):b.cswap(km.q(flag),km.q(q),km.q(r))
 swap();rr=[('L',(q,),0,(r,)) for q,r in zip(n1,u)]+m.prod_rt(u,t,d0);E.mac(rr);reciprocal(b,E,d1)
 with m.opened(E,'lowtemp_low_product',12) as tmp:
  E.mac(m.prod_rt(tmp,u,d1));E.free(rr)
  for q,r in zip(u,tmp):E.b.swap(q,r)
 reciprocal(b,E,d1)
 for q,r in zip(t,u):E.cx(q,r)
 caxpy(m,E,flag,t,u,1);swap()
 with m.eq_test(E,d1,0) as z:E.cx(z,flag)
 b.free(km.array([km.q(flag)]))
