# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Mapped Boolean network -> exact XOR oracle with measured AND cleanup.

ABC supplies the classical logic only. The emitted quantum circuit checks and
repairs every AND erasure and preserves arbitrary incoming output words.
"""
from dataclasses import dataclass
from pathlib import Path
import kickmix as km

@dataclass(frozen=True)
class Signal:
 terms:frozenset
 const:int=0
 def __xor__(self,b):return Signal(self.terms^b.terms,self.const^b.const)
 def __invert__(self):return Signal(self.terms,1-self.const)

ZERO=Signal(frozenset());ONE=~ZERO

class Network:
 def __init__(self,n):self.n=n;self.nodes=[];self.memo={};self.outputs=[]
 def mul(self,a,b):
  if not a.terms:return b if a.const else ZERO
  if not b.terms:return a if b.const else ZERO
  if a.terms==b.terms:return a if a.const==b.const else ZERO
  key=tuple(sorted((a,b),key=lambda x:(tuple(sorted(x.terms)),x.const)))
  if key not in self.memo:
   self.memo[key]=Signal(frozenset([self.n+len(self.nodes)]));self.nodes.append(key)
  return self.memo[key]
 def gate(self,kind,w):
  if kind=='zero':return ZERO
  if kind=='one':return ONE
  a=w.get('a');b=w.get('b');c=w.get('c');s=w.get('s')
  if kind=='buf':return a
  if kind=='inv':return ~a
  if kind=='and2':return self.mul(a,b)
  if kind=='nand2':return ~self.mul(a,b)
  if kind=='or2':return ~self.mul(~a,~b)
  if kind=='nor2':return self.mul(~a,~b)
  if kind=='xor2':return a^b
  if kind=='xnor2':return ~(a^b)
  if kind=='mux2':return a^self.mul(s,a^b)
  if kind=='maj3':return a^self.mul(a^b,a^c)
  if kind=='xorand':return self.mul(a,b^c)
  if kind=='andxor':return a^self.mul(b,c)
  raise ValueError(kind)
 def values(self):
  count=1<<self.n;allbits=(1<<count)-1
  values=[sum(((a>>i)&1)<<a for a in range(count)) for i in range(self.n)]
  def val(s):
   out=allbits if s.const else 0
   for j in s.terms:out^=values[j]
   return out
  for a,b in self.nodes:values.append(val(a)&val(b))
  return [sum(((val(s)>>a)&1)<<i for i,s in enumerate(self.outputs)) for a in range(count)]
 def emit(self,b,address,target,budget=24):
  assert len(address)==self.n and len(target)==len(self.outputs)
  A,B=b.alloc_qubits(2);live={};held={};pins={};age={};tick=0;computed=0;peak=0
  def parents(j):return {p for s in self.nodes[j-self.n] for p in s.terms if p>=self.n}
  def linear(s,q):
   if s.const:b.x(q)
   for j in sorted(s.terms):b.cx(address[j] if j<self.n else live[j],q)
  def erase(j):
   a,c=self.nodes[j-self.n];linear(a,A);linear(c,B);b.del_and(A,B,live[j]);linear(c,B);linear(a,A)
   b.free(km.array([live.pop(j)]));age.pop(j)
   for p in parents(j):held[p]-=1
   held.pop(j);pins.pop(j,None)
  def room():
   while len(live)>=budget:
    choices=[j for j in live if not held[j] and not pins.get(j,0)]
    if not choices:raise ValueError(f'Boolean pebbling needs more than {budget} AND registers')
    erase(min(choices,key=lambda j:age[j]))
  def ensure(j):
   nonlocal tick,computed,peak
   tick+=1
   if j in live:age[j]=tick;return
   pp=sorted(parents(j))
   for p in pp:ensure(p);pins[p]=pins.get(p,0)+1
   room();q=b.alloc_qubits(1)[0];a,c=self.nodes[j-self.n]
   linear(a,A);linear(c,B);b.init_and(A,B,q);linear(c,B);linear(a,A)
   live[j]=q;held[j]=0;age[j]=tick;computed+=1;peak=max(peak,len(live))
   for p in pp:held[p]+=1;pins[p]-=1
  for out,q in zip(self.outputs,target):
   if out.const:b.x(q)
   for j in sorted(out.terms):
    if j>=self.n:ensure(j)
    b.cx(address[j] if j<self.n else live[j],q)
  while live:
   choices=[j for j in live if not held[j]];assert choices
   erase(max(choices))
  b.free(km.array([A,B]));return dict(ANDs=computed,peak_AND_registers=peak,network_ANDs=len(self.nodes))
