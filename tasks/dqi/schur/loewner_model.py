# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Projective Hermite-Schur reconstruction of sparse syndrome moments.

New architectural experiment. Matrix data are an invertible binary-linear
transform of syndrome moments. Finite-point steps are involutive Hermite
Möbius transforms; infinity steps remove one simple pole. No quantum circuit
or resource improvement is claimed by this classical model.
"""
import sys,json,random,time
from pathlib import Path
from .algebra import Field,trim
class FastField(Field):
 def __init__(self):
  super().__init__();self.ex=[];v=1
  for _ in range(4095):self.ex.append(v);v=super().mul(v,2)
  assert len(set(self.ex))==4095
  self.lg=[0]*4096
  for j,v in enumerate(self.ex):self.lg[v]=j
  self.ex=self.ex*3
 def mul(self,a,b):return self.ex[self.lg[a]+self.lg[b]] if a and b else 0
 def pow(self,a,n):return self.ex[self.lg[a]*n%4095] if a else int(n==0)
 def inv(self,a):
  if not a:raise ZeroDivisionError()
  return self.ex[4095-self.lg[a]]

F=FastField()
def fixed(a,n):return a[:n]+[0]*max(0,n-len(a))
def node_maps(nodes):
 P=[1]
 for a in nodes:P=F.product(P,[a,1])
 maps=[]
 for a in nodes:
  q,r=F.divide(P,[a,1]);assert not r
  maps.append((fixed(F.product(P,q),2*len(nodes)),fixed(F.product(q,q),2*len(nodes))))
 return maps

def transform(s,maps):
 def dot(a):
  v=0
  for x,y in zip(a,s):v^=F.mul(x,y)
  return v
 return [(dot(a),dot(b),False) for a,b in maps]

def extract(nodes,data):
 data=list(data);stages=[];exception=None;counts=dict(infinity_entries=0,infinity_pivots=0,completion=0)
 for k,node in enumerate(nodes):
  y0,d0,pole=data[k];completion=False
  if pole:
   counts['infinity_pivots']+=1
   if not d0:exception='multiple_pole';break
   residue=F.inv(d0)
   for j in range(k+1,len(nodes)):
    y,d,inf=data[j];c=nodes[j]^node
    if not inf:data[j]=(y^F.mul(residue,F.inv(c)),d^F.mul(residue,F.inv(F.mul(c,c))),False)
   stages.append(dict(node=node,pole=True,residue=residue,original=(y0,d0,pole)))
  else:
   if not d0:
    if all(y==0 and d==0 and not inf for y,d,inf in data[k:]):d0=1;completion=True;counts['completion']+=1
    else:exception='zero_derivative_pivot';break
   for j in range(k+1,len(nodes)):
    y,d,inf=data[j];c=nodes[j]^node;u=y0^F.mul(c,d0);v=F.mul(F.mul(c,c),F.mul(d0,d0))
    if inf:
     data[j]=(u,d0^F.mul(v,d),False)
    else:
     den=y^u
     if not den:
      data[j]=(0,F.mul(d^d0,F.inv(v)),True);counts['infinity_entries']+=1
     else:
      iv=F.inv(den);data[j]=(u^F.mul(v,iv),d0^F.mul(F.mul(v,F.mul(iv,iv)),d^d0),False)
   stages.append(dict(node=node,pole=False,a=y0,d=d0,completion=completion,original=data[k]))
 return stages,exception,counts

def synthesize(stages):
 N=[];B=[1]
 for s in reversed(stages):
  node=s['node']
  if s['pole']:
   N=F.add(F.product([node,1],N),F.scale(B,s['residue']));B=F.product([node,1],B)
  else:
   u=[s['a']^F.mul(node,s['d']),s['d']]
   N,B=F.add(F.product(u,N),F.scale(B,F.mul(s['a'],s['a']))),F.add(N,F.product(u,B))
 # Completion factors persist through all earlier polynomial matrix products.
 for s in stages:
  if s.get('completion'):
   N,r=F.divide(N,[s['node'],1]);assert not r
   B,r=F.divide(B,[s['node'],1]);assert not r
 if not B:raise AssertionError('zero denominator')
 scale=F.inv(B[-1]);return F.scale(N,scale),F.scale(B,scale)

def check(cases=100,N=70):
 nodes=list(range(N//2));maps=node_maps(nodes);rng=random.Random(142031+N);rows=[];counts=dict(infinity_entries=0,infinity_pivots=0,completion=0);exceptions={};fail=[]
 for trial in range(cases):
  d=trial%(N//2+1);positions=rng.sample(range(1,4096),d)
  if d and trial%3==0:positions[0]=1
  if len(set(positions))<d:continue
  values=[rng.randrange(1,4096) for _ in positions];s=F.syndrome(positions,values,N)
  data=transform(s,maps);stages,exc,c=extract(nodes,data)
  for k,v in c.items():counts[k]+=v
  if exc:exceptions[exc]=exceptions.get(exc,0)+1;continue
  num,den=synthesize(stages);want=[1]
  for aa in positions:want=F.product(want,[aa,1])
  if den!=want:
   fail.append(dict(trial=trial,weight=d,positions=positions,den=den,want=want,num=num,stages=stages));break
  # Check the rational congruence defining the interpolation problem,
  # including roots coincident with interpolation nodes (common factors).
  for node,(y,der,_) in zip(nodes,data):
   bv=F.evaluate(den,node);nv=F.evaluate(num,node);bd=F.evaluate(F.derivative(den),node);nd=F.evaluate(F.derivative(num),node)
   assert nv==F.mul(y,bv)
   assert nd==F.mul(der,bv)^F.mul(y,bd)
  rows.append(dict(weight=d,node_errors=sum(a in nodes for a in positions)))
 result=dict(status='FAIL' if fail else 'MODEL_PASS',N=N,cases=len(rows),counts=counts,exceptions=exceptions,failed_cases=fail,scope='classical finite/projective Hermite-Schur locator reconstruction only')
 Path(f'results/loewner_n{N}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='failed_cases'}),flush=True)
 return result
