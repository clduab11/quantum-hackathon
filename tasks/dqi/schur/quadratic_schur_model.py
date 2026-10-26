# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Degree-two-node Schur decoder: 70 moments, 35 extension-field samples.

Nodes are outside the allowed error field, so the linear moment transform
never loses magnitudes at coinciding interpolation/error positions. Every
node update is translation, GF(2^24) inversion, and classical scaling.
Global affine/scale frames are stored using the two consumed pivot words.
This is independent classical algebra, not a quantum resource claim.
"""
import json,random,time
from pathlib import Path
from .loewner_model import F,fixed
MASK=4095

def trace(a):
 t=0
 for _ in range(12):t^=a;a=F.mul(a,a)
 return t
K=next(a for a in range(1,4096) if trace(a)==1)
def emul(x,y):
 a,b=x&MASK,x>>12;c,d=y&MASK,y>>12
 ac=F.mul(a,c);bd=F.mul(b,d);cross=F.mul(a^b,c^d)^ac
 return (ac^F.mul(K,bd))|(cross<<12)
def einv(x):
 a,b=x&MASK,x>>12
 norm=F.mul(a,a)^F.mul(a,b)^F.mul(K,F.mul(b,b));iv=F.inv(norm)
 return F.mul(a^b,iv)|(F.mul(b,iv)<<12)
def bmul(x,c):return F.mul(x&MASK,c)|(F.mul(x>>12,c)<<12)
def norm(a,b,k):return F.mul(a,a)^F.mul(a,b)^F.mul(k,F.mul(b,b))
def epow(a,n):
 v=1
 while n:
  if n&1:v=emul(v,a)
  a=emul(a,a);n>>=1
 return v

def node_maps(n):
 nodes=[(2*i)|(1<<12) for i in range(n)];kap=[F.mul(2*i,2*i)^(2*i)^K for i in range(n)]
 assert len(set(kap))==n
 P=[1]
 for k in kap:P=F.product(P,[k,1,1])
 maps=[]
 for alpha in nodes:
  q=[0]*(2*n);q[-1]=P[-1]
  for j in reversed(range(2*n-1)):q[j]=P[j+1]^emul(alpha,q[j+1])
  assert P[0]^emul(alpha,q[0])==0
  maps.append(q)
 return nodes,kap,P,maps

def transform(s,maps):
 out=[]
 for q in maps:
  v=0
  for c,x in zip(q,s):v^=bmul(c,x)
  out.append(v)
 return out

def extract(nodes,kap,data,allow_swap=False):
 nodes=list(nodes);kap=list(kap);v=list(data);g=1;A=B=0;stages=[];counts=dict(completion=0,swaps=0);exc=None
 for i in range(len(nodes)):
  def pivot(j):
   b=v[j]>>12;a=(v[j]&MASK)^F.mul(nodes[j]&MASK,b)
   return a,b,F.mul(g,a)^A,F.mul(g,b)^B
  a,b,aF,bF=pivot(i)
  if not bF and aF:
   if allow_swap and i+1<len(nodes) and pivot(i+1)[3]:
    nodes[i],nodes[i+1]=nodes[i+1],nodes[i];kap[i],kap[i+1]=kap[i+1],kap[i];v[i],v[i+1]=v[i+1],v[i];a,b,aF,bF=pivot(i);counts['swaps']+=1
   else:exc='zero_schur_pivot';break
  if not aF and not bF:
   if any(bmul(v[j],g)^A^bmul(nodes[j],B) for j in range(i,len(nodes))):exc='false_completion';break
   counts['completion']=len(nodes)-i;break
  for j in range(i+1,len(nodes)):
   den=v[j]^a^bmul(nodes[j],b)
   if not den:exc='extension_pole';break
   v[j]=bmul(einv(den),kap[i]^kap[j])
  if exc:break
  stages.append(dict(a=aF,b=bF,kappa=kap[i],node=nodes[i],raw_a=a,raw_b=b))
  oldg=g;g=F.mul(F.mul(bF,bF),F.inv(oldg));A=aF^bF;B=bF
 return stages,exc,counts

def synthesize(stages):
 N=[];B=[1]
 for s in reversed(stages):
  u=[s['a'],s['b']];bar=[s['a']^s['b'],s['b']];nn=norm(s['a'],s['b'],s['kappa'])
  N,B=F.add(F.product(u,N),F.scale(B,nn)),F.add(N,F.product(bar,B))
 scale=F.inv(B[-1]);return F.scale(N,scale),F.scale(B,scale)

def check(N,cases,swap):
 n=N//2;nodes,kap,P,maps=node_maps(n);rng=random.Random(142033+N);counts=dict(completion=0,swaps=0);fail=[];exceptions={};good=0;weights=[];start=time.time()
 for trial in range(cases):
  d=trial%(n+1);pos=rng.sample(range(1,4096),d);val=[rng.randrange(1,4096) for _ in pos];s=F.syndrome(pos,val,N);v=transform(s,maps)
  stages,exc,cc=extract(nodes,kap,v,swap)
  for k,x in cc.items():counts[k]+=x
  if exc:exceptions[exc]=exceptions.get(exc,0)+1;continue
  num,den=synthesize(stages);want=[1]
  for a in pos:want=F.product(want,[a,1])
  if den!=want:
   fail.append(dict(trial=trial,degree=d,den=den,want=want,stages=stages));break
  for a,e in zip(pos,val):
   residue=F.mul(F.evaluate(num,a),F.inv(F.evaluate(F.derivative(den),a)))
   got=F.mul(residue,F.inv(F.mul(a,F.evaluate(P,a))))
   assert got==e,(a,e,got)
  for alpha,vv in zip(nodes,v):
   nv=0;bv=0
   for c in reversed(num):nv=emul(nv,alpha)^c
   for c in reversed(den):bv=emul(bv,alpha)^c
   assert nv==emul(vv,bv)
  good+=1;weights.append(d)
 result=dict(status='FAIL' if fail else 'MODEL_PASS',N=N,cases=good,counts=counts,exceptions=exceptions,failed_cases=fail,allow_swap=swap,seconds=time.time()-start,scope='exact sparse moment decoding and magnitudes; no quantum circuit',extension_modulus_kappa=K)
 Path(f'results/quadratic_schur_n{N}_swap{int(swap)}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='failed_cases'}),flush=True)
 return result
