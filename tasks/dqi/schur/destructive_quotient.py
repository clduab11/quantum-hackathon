# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Demolish a polynomial remainder while recovering its extension quotient.

Inputs satisfy num=head*den on the supported polynomial-fold chart. Their
measurement phase is repaid by that bilinear identity after quotient creation.
"""
import kickmix as km
from .extension_inverse import setup,inverse_output_rt
from .low_workspace_inverse import norm_rt as norm12_rt
from .schur_dynamic_division_compact import numerator,norm_rt
from .cubic_mask_phase_compact import native_phase_inverse
from .tower_inverse import apply_map,map_ops


def power5_rt(m,src,target):
 images={m._elt3(i):i for i in range(8)};values=[images[m.gpow(m._elt3(i),5)] for i in range(8)]
 for j in range(3):
  for i in range(8):
   if i>>j&1:values[i]^=values[i^(1<<j)]
 rt=[]
 for mask,c in enumerate(values):
  if not c:continue
  dst=tuple(target[j] for j in range(3) if c>>j&1);ii=[i for i in range(3) if mask>>i&1];assert len(ii) in [1,2]
  rt.append(('L',(src[ii[0]],),0,dst) if len(ii)==1 else ('P',(src[ii[0]],),0,(src[ii[1]],),0,dst))
 return rt


def inverse_into(m,E,src,out):
 n=E.A.open('destroy_N6',6);mm=E.A.open('destroy_M3',3);s=E.A.open('destroy_S3',3)
 # The cube M^3 is invertible; M=(M^3)^5 is quadratic over GF8.
 rN,rM,rS=m.norm_chain_terms(src,m.spec_rows(m.A0ROWS,src),m.spec_rows(m.A1ROWS,src),n,mm,s);E.macs([rN,rM,rS]);E.free(power5_rt(m,s,mm));E.A.close('destroy_M3',mm)
 y=E.A.open('destroy_Y6',6);rY=m.chain_rts(src,[n,mm,s,y],out)[-2];E.mac(rY)
 # Norm(N^-1)=M^-1=(M^3)^2. Erase the squared cube from the inverse.
 apply_map(E.b.raw,km.array([km.q(q) for q in s]),map_ops(m.SQ3R));rr=[];m.bil_terms(rr,m.KT3,m.spec_plain(y[:3]),m.spec_plain(y[3:]),s);m.lin_rows_terms(rr,m.LMROWS,y,s);E.free(rr);E.A.close('destroy_S3',s);E.free(rN);E.A.close('destroy_N6',n)
 E.mac(inverse_output_rt(m,src,y,out));E.free(norm12_rt(m,out,y));E.A.close('destroy_Y6',y)


def phase_terms(E,rt,mask_by_target):
 for t in rt:
  for tw in t[-1]:
   bit=mask_by_target[tw]
   if t[0]=='L':
    for q in t[1]:E.b.z(q,bit)
    if t[2]:E.b.neg(bit)
   else:E.pivot_pair(t[1],t[2],t[3],t[4],lambda a,b:E.b.cz(a,b,bit))


def product_rt(m,left,right,out,kappa):
 a,c=left[:12],left[12:];d,e=right[:12],right[12:];rt=m.prod_rt(out[:12],a,d)+m.prod_rt(out[12:],a,e)+m.prod_rt(out[12:],c,d)
 def targets(js):
  v=m.gmul(kappa,sum(1<<j for j in js));return [out[j] for j in range(12) if v>>j&1]+[out[12+j] for j in js]
 m.bil_terms(rt,m.KT,m.spec_plain(c),m.spec_plain(e),tws_of=targets);return rt


def create(b,E,num,den,out,kappa):
 m=setup()[0]
 with numerator(b,E,num,den,out,kappa,[],keep=True):pass
 mask=b.alloc_bits(24);b.hmr(km.array([km.q(q) for q in num]),mask);nn,ni=num[:12],num[12:];nr=norm_rt(m,den,nn,kappa,[]);E.mac(nr);inverse_into(m,E,nn,ni)
 with m.opened(E,'destroy_scale',12) as tmp:
  for word in [out[:12],out[12:]]:m.mon_slot(E,word,ni,nn,tmp)
 im=b.alloc_bits(12);b.hmr(km.array([km.q(q) for q in ni]),im);native_phase_inverse(b,nn,im);b.bit_store(im,False);b.free(im);E.free(nr)
 phase_terms(E,product_rt(m,out,den,num,kappa),{q:bit for q,bit in zip(num,mask)});b.bit_store(mask,False);b.free(mask)


