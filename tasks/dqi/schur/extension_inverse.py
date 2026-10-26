# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Low-workspace in-place inversion in GF(4096)[t]/(t²+t+kappa).

Uses the attributed 42-AND native multiplier and 76-AND inverse creation,
then repays old-input measurements with a transposed tower inverse parity.
Output and input are the same 24 quantum wires. Zero maps to zero.
"""
from functools import lru_cache
import json
from pathlib import Path
import numpy as np
import kickmix as km
from .import_published import load
from .published_dqi import isomorphism
from .low_workspace_inverse import norm_rt as norm12_rt,inverse_output_rt
from .tower_inverse import map_ops,apply_map
from .recursive_forney import inverse_dot_data
from .transposed_forney import multiplication_terms
from .crt_multiplier import indices

def classical_transpose(b,x,u,target):
 flag=b.alloc_bits(1)[0];b.bit_store(flag,False)
 for lm,rm,om in multiplication_terms(len(x)):
  xx=list(indices(lm));lead=x[xx[0]];other=km.array([x[j] for j in xx[1:]])
  cm=km.array([u[j] for j in indices(om)]);dst=km.array([target[j] for j in indices(rm)])
  b.cx(other,lead);b.cx(cm,flag);b.push_condition(flag);b.cx(lead,dst);b.pop_condition();b.cx(cm,flag);b.cx(other,lead)
 b.bit_store(flag,False);b.free(km.array([flag]))

class TrackBits:
 def __init__(self,b):self.raw=b;self.used=set()
 def __getattr__(self,name):return getattr(self.raw,name)
 def alloc_bits(self,n):
  bits=self.raw.alloc_bits(n);self.used.update(v.id for v in bits);return bits

class Adapter:
 def __init__(self,b):self.raw=b;self.outcomes=[]
 @property
 def active_qubits(self):return self.raw.num_allocated_qubits
 def qubits(self,n):return [q.id for q in self.raw.alloc_qubits(n)]
 def claim(self,*args):pass
 def release_recycle(self,name,words):self.raw.free(km.array([km.q(i) for i in words]))
 def x(self,q,cond=None):
  if cond is not None:self.raw.push_condition(cond)
  self.raw.x(km.q(q))
  if cond is not None:self.raw.pop_condition()
 def cx(self,c,t,cond=None):
  if cond is not None:self.raw.push_condition(cond)
  self.raw.cx(km.q(c),km.q(t))
  if cond is not None:self.raw.pop_condition()
 def ccx(self,a,b,t,cond=None):
  if cond is not None:self.raw.push_condition(cond)
  self.raw.ccx(km.q(a),km.q(b),km.q(t))
  if cond is not None:self.raw.pop_condition()
 def z(self,q,cond=None):
  if cond is not None:self.raw.push_condition(cond)
  self.raw.z(km.q(q))
  if cond is not None:self.raw.pop_condition()
 def cz(self,a,b,cond=None):
  if cond is not None:self.raw.push_condition(cond)
  self.raw.cz(km.q(a),km.q(b))
  if cond is not None:self.raw.pop_condition()
 def neg(self,cond=None):
  if cond is not None:self.raw.push_condition(cond)
  self.raw.z(True)
  if cond is not None:self.raw.pop_condition()
 def swap(self,a,b):self.raw.swap(km.q(a),km.q(b))
 def hmr(self,q):
  m=self.raw.alloc_bits(1)[0];self.raw.bit_store(m,False);self.raw.hmr(km.q(q),m);self.outcomes.append(m);return m

@lru_cache(None)
def setup():
 m=load()
 def trace(a):
  out=0
  for _ in range(12):out^=a;a=m.gmul(a,a)
  return out
 fw,bk,tr=isomorphism(m)
 # Match the independent Schur model's t²+t+2048 over the host field.
 k=tr(2048,fw);assert trace(k)==1
 return m,k,fw,bk,tr

def linear_rt(m,source,target,columns):
 rows=[sum(((v>>j)&1)<<i for i,v in enumerate(columns)) for j in range(len(target))];rt=[]
 m.lin_rows_terms(rt,rows,source,target);return rt

def extension_norm_rt(m,source,target,kappa):
 a,b=source[:12],source[12:];rt=m.prod_rt(target,a,b)
 rt+=linear_rt(m,a,target,[m.gmul(1<<i,1<<i) for i in range(12)])
 rt+=linear_rt(m,b,target,[m.gmul(kappa,m.gmul(1<<i,1<<i)) for i in range(12)])
 return rt

def init_inverse12(m,E,src,out):
 names=[('ext_inv_N6',6),('ext_inv_M3',3),('ext_inv_S3',3),('ext_inv_Y6',6)]
 wins=[E.A.open(name,n) for name,n in names];n,mm,s,y=wins
 rN,rM,rS=m.norm_chain_terms(src,m.spec_rows(m.A0ROWS,src),m.spec_rows(m.A1ROWS,src),n,mm,s)
 rY=m.chain_rts(src,wins,src)[-2]
 E.macs([rN,rM,rS,rY]);E.frees([rN,rM,rS])
 for (name,_),word in reversed(list(zip(names[:3],wins[:3]))):E.A.close(name,word)
 E.mac(inverse_output_rt(m,src,y,out));E.free(norm12_rt(m,out,y));E.A.close(names[3][0],y)

def init_extension_inverse(m,E,source,out,kappa):
 with m.opened(E,'extension_norm',12) as nn,m.opened(E,'extension_norm_inverse',12) as ni:
  nr=extension_norm_rt(m,source,nn,kappa);E.mac(nr)
  init_inverse12(m,E,nn,ni)
  left=[a^b for a,b in zip(m.spec_plain(source[:12]),m.spec_plain(source[12:]))]
  rt=[];m.bil_terms(rt,m.KT,left,m.spec_plain(ni),out[:12]);E.mac(rt)
  E.mac(m.prod_rt(out[12:],source[12:],ni))
  E.free(extension_norm_rt(m,out,ni,kappa));E.free(nr)

def inverse_phase(b,E,source,mask,kappa):
 """mask dot inverse(source), with source stored in native tower coordinates."""
 m,_,fw,bk,tr=setup();a,c=source[:12],source[12:]
 with m.opened(E,'extension_phase_norm',12) as nn:
  rt=extension_norm_rt(m,source,nn,kappa);E.mac(rt)
  aa=km.array([km.q(i) for i in a]);cc=km.array([km.q(i) for i in c]);nr=km.array([km.q(i) for i in nn])
  # Native polynomial bits -> host polynomial bits. Classical masks use
  # the transpose of the opposite (host -> native) coordinate transform.
  fops=map_ops(fw);bops=map_ops(bk);trans=tuple(sum(((fw[i]>>j)&1)<<i for i in range(12)) for j in range(12));mops=map_ops(trans)
  for word in [aa,cc,nr]:apply_map(b,word,bops)
  for word in [mask[:12],mask[12:]]:apply_map(b,word,mops)
  u=b.alloc_qubits(12)
  def umap():
   b.cx(cc,aa);classical_transpose(b,aa,mask[:12],u);b.cx(cc,aa)
   classical_transpose(b,cc,mask[12:],u)
  umap();leaf,inv,cleanup=inverse_dot_data(b,nr,u);b.cz(leaf,inv);cleanup();umap();b.free(u)
  for word in [mask[:12],mask[12:]]:apply_map(b,word,mops,True)
  for word in [aa,cc,nr]:apply_map(b,word,bops,True)
  E.free(rt)

def _inplace_body(b,source):
 """Internal body; build() adds the required private-classical reset boundary."""
 b=TrackBits(b)
 m,k,fw,bk,tr=setup();ab=Adapter(b);scratch=ab.qubits(3);E=m.Em(ab,*scratch,m.Alloc(ab));src=[q.id for q in source]
 out=ab.qubits(24);init_extension_inverse(m,E,src,out,k)
 measurements=b.alloc_bits(24);b.hmr(source,measurements)
 inverse_phase(b,E,out,measurements,k)
 b.bit_store(measurements,False);b.free(measurements)
 for a,c in zip(src,out):ab.swap(a,c)
 ab.release_recycle('out',out);ab.release_recycle('emitter',scratch)
 b.bit_store(km.array([km.b(i) for i in sorted(b.used)]),False)

def build():
 from .fast_dqi import FastBuilder
 b=FastBuilder(km.CircuitBuilder());x=b.create_quantum_register(24,'x');_inplace_body(b,x);c=b.finish_circuit()
 # The native inverse helper allocates additional classical outcomes inside
 # C++; clear all private bits at the standalone component boundary.
 return km.Circuit(str(c)+'\n'+''.join(f'BIT_STORE0 b{i}\n' for i in range(c.num_bits)))

