# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Two-payload inverse Bezout transform through a generic Euclidean chart.

Sources are restored. Zero pivots are reversibly armed, defining a supported
permutation but not the desired Bezout map on degree-gap charts.
"""
from contextlib import contextmanager
import argparse,json,time
from pathlib import Path
import numpy as np
import kickmix as km
from .extension_inverse import Adapter,setup
from .low_workspace_inverse import bind
from .fast_dqi import FastBuilder


def divide(m,E,f,g,inverse=False,one=False,provided_inverse=None):
 n=len(g)-1;mm=len(f)-1
 @contextmanager
 def inv():
  if one:yield None
  elif provided_inverse is not None:yield provided_inverse
  else:
   with m.inv_word(E,g[-1]) as gi:yield gi
 with inv() as gi,m.opened(E,'bez_source_divide',12) as tmp:
  for i in (range(n,mm+1) if inverse else reversed(range(n,mm+1))):
   if not inverse and not one:m.mon_slot(E,f[i],gi,g[-1],tmp)
   for j in range(n):E.mac(m.prod_rt(f[i-n+j],f[i],g[j]))
   if inverse and not one:m.mon_slot(E,f[i],g[-1],gi,tmp)


def companion(m,E,f,payloads,flag,inverse=False):
 b=E.b.raw;size=len(payloads[0])
 def rotate(back=False):
  for y in payloads:
   for i in (range(size-1) if back else reversed(range(size-1))):
    for q,r in zip(y[i],y[i+1]):b.cswap(km.q(flag),km.q(q),km.q(r))
 if not inverse:rotate()
 # Process each vector separately to keep temporary field width bounded.
 for y in payloads:
  with m.opened(E,'bez_companion_mask',12) as masked:
   mr=[('P',(flag,),0,(q,),0,(r,)) for q,r in zip(y[0],masked)];E.mac(mr)
   source=f[0] if inverse else f[-1];eraser=f[-1] if inverse else f[0]
   with m.inv_word(E,source) as si,m.opened(E,'bez_companion_scale',12) as tmp:m.mon_slot(E,masked,si,source,tmp)
   rt=[];m.bil_terms(rt,m.KT,m.spec_plain(masked),[a^c for a,c in zip(m.spec_plain(f[0]),m.spec_plain(f[-1]))],y[0]);E.mac(rt)
   for i in range(1,size):E.mac(m.prod_rt(y[i],masked,f[i]))
   with m.inv_word(E,eraser) as ei,m.opened(E,'bez_companion_recover',12) as original:
    rr=m.prod_rt(original,y[0],ei);E.mac(rr);E.free([('P',(flag,),0,(q,),0,(r,)) for q,r in zip(original,masked)]);E.free(rr)
 if inverse:rotate(True)


def apply(m,E,f,g,payloads,inverse=False,g_one=False,history=None):
 mm,n=len(f)-1,len(g)-1;assert all(len(v)==mm for v in payloads) and mm>=n>=0
 if mm==n:
  divide(m,E,f,g,one=g_one);apply(m,E,g,f[:n],payloads,inverse,history=history);divide(m,E,f,g,True,g_one);return
 assert mm==n+1
 if not n:
  with m.opened(E,'bez_terminal_pivot',12) as d:
   rt=m.prod_rt(d,f[-1],g[-1]);E.mac(rt)
   with m.inv_word(E,d) as di,m.opened(E,'bez_terminal_scale',12) as tmp:
    for y in payloads:m.mon_slot(E,y[-1],d if inverse else di,di if inverse else d,tmp)
   E.free(rt)
  return
 b=E.b.raw;index,flag=history;code=mm
 def detect():
  with m.eq_test(E,index,0) as z0,m.eq_test(E,g[-1],0) as zg:E.b.ccx(z0,zg,flag)
 def store():
  for i,q in enumerate(index):
   if code>>i&1:E.cx(flag,q)
 def query():b.flip_if_equal(km.array([km.q(q) for q in index]),code,target=km.q(flag))
 def rotate(back=False):
  for i in (range(n) if back else reversed(range(n))):
   for q,r in zip(g[i],g[i+1]):b.cswap(km.q(flag),km.q(q),km.q(r))
 detect();store()
 if not inverse:companion(m,E,f,payloads,flag)
 rotate()
 query()
 if True:
  def scale_last(scale,eraser):
   with m.opened(E,'bez_fast_scale',12) as tmp:
    for y in payloads:m.mon_slot(E,y[-1],scale,eraser,tmp)
  def cross(post=False):
   for i in range(n):
    for y in payloads:E.mac(m.prod_rt(y[-1] if post else y[i],g[i],y[i] if post else y[-1]))
  if not n:
   with m.opened(E,'bez_fast_pivot',12) as d:
    rt=m.prod_rt(d,f[-1],g[-1]);E.mac(rt)
    with m.inv_word(E,d) as di:scale_last(d if inverse else di,di if inverse else d)
    E.free(rt)
  else:
   with m.inv_word(E,g[-1]) as gi:
    scale_last(g[-1] if inverse else gi,gi if inverse else g[-1]);cross(inverse);divide(m,E,f,g,provided_inverse=gi)
   if inverse:apply(m,E,g,f[:n],[y[:n] for y in payloads],True,history=history)
   with m.inv_word(E,f[-1]) as qi:scale_last(f[-1] if inverse else qi,qi if inverse else f[-1])
   if not inverse:apply(m,E,g,f[:n],[y[:n] for y in payloads],history=history)
   with m.inv_word(E,g[-1]) as gi:
    divide(m,E,f,g,True,provided_inverse=gi);cross(not inverse);scale_last(g[-1] if inverse else gi,gi if inverse else g[-1])
 query();rotate(True)
 if inverse:companion(m,E,f,payloads,flag,True)
 store();detect()


def build(t,inverse=False):
 m=setup()[0];m.inv_word=bind(m);b=FastBuilder(km.CircuitBuilder());ff=[b.create_quantum_register(12,f'f{i}') for i in range(t+1)];gg=[b.create_quantum_register(12,f'g{i}') for i in range(t)];ys=[[b.create_quantum_register(12,f'y{p}_{i}') for i in range(t)] for p in range(2)];ab=Adapter(b);sc=ab.qubits(3);E=m.Em(ab,*sc,m.Alloc(ab));lead=E.A.open('bez_monic_lead',12);E.x(lead[0]);index=E.A.open('bez_gap_index',max(1,t.bit_length()));flag=E.A.open('bez_gap_flag',1)[0];apply(m,E,[[q.id for q in w] for w in ff],[[q.id for q in w] for w in gg]+[lead],[[[q.id for q in w] for w in bank] for bank in ys],inverse,True,(index,flag));E.A.close('bez_gap_flag',[flag]);E.A.close('bez_gap_index',index);E.x(lead[0]);E.A.close('bez_monic_lead',lead);ab.release_recycle('bez_emitter',sc);c=b.finish_circuit();return km.Circuit(str(c)+'\n'+''.join(f'BIT_STORE0 b{i}\n' for i in range(c.num_bits)))


