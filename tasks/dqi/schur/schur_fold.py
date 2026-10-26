# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Reversible in-place synthesis of one quadratic Schur factor.

A monic proper degree-d rational pair and (a,b) become a monic proper
degree-(d+1) pair. Two output words are added, and the two pivot words
are measured and repaid using R_new(alpha)=a+b*alpha. Completion (a=b=0)
uses zero coefficient padding, supported when the tail is identically zero.
The classical model records unsupported zero pivots and extension poles.
"""
import argparse,json
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import numpy as np
import kickmix as km
from .extension_inverse import Adapter,setup
from .extension_division import create as divide_create,phase as divide_phase
from .low_workspace_inverse import bind
from .tower_inverse import map_ops
from .fast_dqi import FastBuilder


def axpy(b,source,target,c,m):
 for i,q in enumerate(source):
  v=m.gmul(c,1<<i)
  for j in range(12):
   if v>>j&1:b.cx(q,target[j])
def xword(b,word,value):
 for i,q in enumerate(word):
  if value>>i&1:b.x(q)

@lru_cache(None)
def dops(d,kappa):
 m=setup()[0];cols=[]
 for w in range(2*d):
  for bit in range(12):
   i=w%d;v=1<<bit;c=0
   if w<d:
    c^=v<<(12*(d+i))
    if i+1<d:c^=v<<(12*(i+1))
   else:
    c^=m.gmul(kappa,v)<<(12*i);c^=v<<(12*(d+i))
    if i+1<d:c^=v<<(12*(d+i+1))
   cols.append(c)
 return map_ops(cols) if d else ()

@contextmanager
def evaluate(b,nn,bb,kappa):
 """Use the first two coefficients as extension evaluation registers."""
 m=setup()[0];degree=len(nn);extras=None
 if degree==1:
  extras=b.alloc_qubits(24);n1=extras[:12];b1=extras[12:];n=[nn[0],n1];den=[bb[0],b1]
 else:n=nn[:2];den=bb[:2]
 powers=[(1,0),(0,1)]
 for _ in range(2,degree+1):
  a,c=powers[-1];powers.append((m.gmul(kappa,c),a^c))
 def run():
  for src,dst in [(nn,n),(bb,den)]:
   for j in range(2,degree):
    axpy(b,src[j],dst[0],powers[j][0],m);axpy(b,src[j],dst[1],powers[j][1],m)
  xword(b,den[0],powers[degree][0]);xword(b,den[1],powers[degree][1])
 run()
 yield [q.id for word in n for q in word],[q.id for word in den for q in word]
 run()
 if extras is not None:b.free(extras)


def arithmetic(b,E,aa,bs,nn,bb,nt,bt,kappa,inverse=False):
 m=setup()[0];m.inv_word=bind(m);A=[q.id for q in aa];B=[q.id for q in bs];d=len(nn)
 # The zero branch is an invertible arithmetic extension. On the valid
 # completed tail all lower coefficients and both pivots are zero.
 with m.eq_test(E,B,0) as z:
  def original_linear():
   b.cx(aa,nt);axpy(b,bs,nt,kappa,m)
  if not inverse:original_linear()
  E.cx(z,B[0])
  with m.inv_word(E,B) as bi,m.opened(E,'fold_product',12) as temp,m.opened(E,'fold_ratio',12) as r:
   rr=m.prod_rt(r,A,bi);E.mac(rr)
   def top():
    if d:b.cx(nn[-1],nt);b.cx(bb[-1],bt)
    E.mac(m.prod_rt([q.id for q in nt],A,r));b.cx(km.array([km.q(q) for q in r]),bt);b.x(bt[0]);E.cx(z,bt[0].id)
   if not inverse:top()
   for n,v in zip(nn,bb):
    N=[q.id for q in n];V=[q.id for q in v];E.mac(m.prod_rt(N,A,V));m.mon_slot(E,N,bi,B,temp)
   words=[q for word in nn+bb for q in word];ops=dops(d,kappa)
   for op,i,j in (reversed(ops) if inverse else ops):getattr(b,op)(words[i],words[j])
   for n,v in zip(nn,bb):
    N=[q.id for q in n];V=[q.id for q in v];m.mon_slot(E,N,B,bi,temp);E.mac(m.prod_rt(N,A,V))
   if inverse:top()
   E.free(rr)
  E.cx(z,B[0])
  if inverse:original_linear()


def build(d,kappa,inverse=False):
 m=setup()[0];b=FastBuilder(km.CircuitBuilder());a=b.create_quantum_register(12,'a');bb=b.create_quantum_register(12,'b')
 nn=[b.create_quantum_register(12,f'N{i}') for i in range(d)];den=[b.create_quantum_register(12,f'B{i}') for i in range(d)]
 nt=b.create_quantum_register(12,'Nt');bt=b.create_quantum_register(12,'Bt');ab=Adapter(b);sc=ab.qubits(3);E=m.Em(ab,*sc,m.Alloc(ab))
 if inverse:
  with evaluate(b,nn+[nt],den+[bt],kappa) as (nv,dv):divide_create(b,E,nv,dv,[q.id for word in [a,bb] for q in word],kappa)
  arithmetic(b,E,a,bb,nn,den,nt,bt,kappa,True)
 else:
  arithmetic(b,E,a,bb,nn,den,nt,bt,kappa)
  mask=b.alloc_bits(24);b.hmr(km.array(list(a)+list(bb)),mask)
  with evaluate(b,nn+[nt],den+[bt],kappa) as (nv,dv):divide_phase(b,E,nv,dv,mask,kappa)
  b.bit_store(mask,False);b.free(mask)
 ab.release_recycle('fold_emitter',sc);c=b.finish_circuit()
 return km.Circuit(str(c)+'\n'+''.join(f'BIT_STORE0 b{i}\n' for i in range(c.num_bits)))


def reference(a,b,n,den,kappa):
 m=setup()[0];d=len(n);r=m.gmul(a,m.ginv(b or 1));c=m.gmul(a,r)^a^m.gmul(kappa,b);active=int(bool(b));h=m.ginv(b or 1)
 if b==0:
  assert not a and not any(n+den)
  return [0]*(d+1),[0]*(d+1)
 no=[0]*(d+1);bo=[0]*(d+1)
 for i in range(d+1):
  v=den[i] if i<d else 1;u=n[i] if i<d else 0
  no[i]=m.gmul(r,u)^m.gmul(c,v)^(n[i-1] if i else 0)
  bo[i]=m.gmul(h,u)^m.gmul(r^active,v)^(den[i-1] if i else 0)
 return no,bo


