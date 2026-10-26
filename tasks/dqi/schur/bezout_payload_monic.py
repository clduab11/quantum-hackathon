# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Implicit monic top level for the two-payload Bezout transform."""
from contextlib import contextmanager
import kickmix as km
from .triangular_dp import DPArithmetic
from .bezout_payload_batched import apply as recurse


def companion(m,E,f,payloads,flag,inverse=False):
 b=E.b.raw;size=len(payloads[0])
 def rotate(back=False):
  for y in payloads:
   for i in (range(size-1) if back else reversed(range(size-1))):
    for q,r in zip(y[i],y[i+1]):b.cswap(km.q(flag),km.q(q),km.q(r))
 if not inverse:rotate()
 with m.inv_word(E,f[0]) as fi:
  for y in payloads:
   with m.opened(E,'monic_companion_mask',12) as masked:
    E.mac([('P',(flag,),0,(q,),0,(r,)) for q,r in zip(y[0],masked)])
    if inverse:
     with m.opened(E,'monic_companion_scale',12) as tmp:m.mon_slot(E,masked,fi,f[0],tmp)
    E.mac(m.prod_rt(y[0],masked,f[0]));
    for q,r in zip(masked,y[0]):E.cx(q,r)
    for i in range(1,size):E.mac(m.prod_rt(y[i],masked,f[i]))
    if inverse:E.free([('P',(flag,),0,(q,),0,(r,)) for q,r in zip(y[0],masked)])
    else:
     with m.opened(E,'monic_companion_recover',12) as original:
      rr=m.prod_rt(original,y[0],fi);E.mac(rr);E.free([('P',(flag,),0,(q,),0,(r,)) for q,r in zip(original,masked)]);E.free(rr)
 if inverse:rotate(True)


def monic_divide(m,E,f,g,gi,inverse=False):
 n=len(g)-1;assert len(f)==n+1
 math=DPArithmetic(m,E)
 def update():
  if n<4:
   for i in range(n):
    E.mac(m.prod_rt(f[i],f[n],g[i]))
    if i:E.mac(m.prod_rt(f[i],gi,g[i-1]))
  else:
   pts,I=m.vinv(n+1)
   for a,point in enumerate(pts):
    left=math.spec([(1,f[n],1),(point,gi,1)]);right=math.spec([(m.gpow(point,i),word,1) for i,word in enumerate(g[:-1])])
    def targets(tb):return [f[i][k] for i in range(n) for k in m.bitlist(m.gmul(I[i][a],m.tmask(tb)),12)]
    math.product(left,right,targets)
 with m.opened(E,'monic_divide_tmp',12) as tmp:
  if inverse:
   update();m.mon_slot(E,f[n],g[-1],gi,tmp);E.mac(m.prod_rt(f[n],gi,g[n-1]))
  else:
   E.mac(m.prod_rt(f[n],gi,g[n-1]));m.mon_slot(E,f[n],gi,g[-1],tmp);update()


def top(m,E,f,g,payloads,inverse,history):
 mm=len(f);n=mm-1;assert len(g)==mm
 def scale(s,e):
  with m.opened(E,'monic_payload_scale',12) as tmp:
   for y in payloads:m.mon_slot(E,y[-1],s,e,tmp)
 if not n:
  with m.inv_word(E,g[0]) as gi:scale(g[0] if inverse else gi,gi if inverse else g[0])
  return
 b=E.b.raw;index,flag=history;code=mm
 def detect():
  with m.eq_test(E,index,0) as zi,m.eq_test(E,g[-1],0) as zg:E.b.ccx(zi,zg,flag)
 def store():
  for i,q in enumerate(index):
   if code>>i&1:E.cx(flag,q)
 def query():b.flip_if_equal(km.array([km.q(q) for q in index]),code,target=km.q(flag))
 def rotate(back=False):
  for i in (range(n) if back else reversed(range(n))):
   for q,r in zip(g[i],g[i+1]):b.cswap(km.q(flag),km.q(q),km.q(r))
 def cross(post=False):
  for i in range(n):
   for y in payloads:E.mac(m.prod_rt(y[-1] if post else y[i],g[i],y[i] if post else y[-1]))
 detect();store()
 if not inverse:companion(m,E,f,payloads,flag)
 rotate();query()
 with m.inv_word(E,g[-1]) as gi:
  scale(g[-1] if inverse else gi,gi if inverse else g[-1]);cross(inverse);monic_divide(m,E,f,g,gi)
  if not inverse:scale(g[-1],gi)
 recurse(m,E,g,f[:n],[y[:n] for y in payloads],inverse,history=history)
 with m.inv_word(E,g[-1]) as gi:
  if inverse:scale(gi,g[-1])
  monic_divide(m,E,f,g,gi,True);cross(not inverse);scale(g[-1] if inverse else gi,gi if inverse else g[-1])
 query();rotate(True)
 if inverse:companion(m,E,f,payloads,flag,True)
 store();detect()


def apply(m,E,f,g,payloads,inverse=False,history=None):
 assert len(f)==len(g)+1
 for i in range(len(g)):E.mac(m.prod_rt(f[i],f[-1],g[i]))
 top(m,E,g,f[:-1],payloads,inverse,history)
 for i in range(len(g)):E.mac(m.prod_rt(f[i],f[-1],g[i]))
