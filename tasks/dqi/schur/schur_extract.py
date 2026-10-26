# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Native reversible extraction of quadratic-node Schur pivots.

Reuses tested inverse/pivot templates with explicitly disjoint quantum
scratch and reset private classical bits at each component boundary. The
component overwrites syndrome words with pivots; it is not a phase oracle.
"""
import argparse,json,re,time
from pathlib import Path
import numpy as np
import kickmix as km
from .tower_inverse import map_ops
from .extension_inverse import build as inverse24,setup
from .schur_pivot import build as pivot
from .quadratic_schur_model import F,node_maps,transform

QRE=re.compile(r'\bq(\d+)\b');BRE=re.compile(r'\bb(\d+)\b')
def body(c):return [line for line in str(c).splitlines() if not line.startswith(('REGISTER','APPEND_TO_REGISTER','INFO_TAG'))]
def mapped(lines,qmap):
 return '\n'.join(QRE.sub(lambda x:f'q{qmap[int(x[1])]}',line) for line in lines)+'\n'

def linear_map(N):
 m,k,fw,bk,tr=setup();nodes,kap,P,maps=node_maps(N//2);cols=[]
 for j in range(N):
  for bit in range(12):
   x=1<<bit;col=0
   for i,q in enumerate(maps):
    v=q[j];lo=tr(F.mul(v&4095,x),fw);hi=tr(F.mul(v>>12,x),fw)
    col^=(lo|(hi<<12))<<(24*i)
   cols.append(col)
 return map_ops(cols)

def axpy_text(source,target,constant,m):
 out=[]
 for i,q in enumerate(source):
  value=m.gmul(constant,1<<i)
  for j in range(12):
   if value>>j&1:out.append(f'CX q{q} q{target[j]}\n')
 return ''.join(out)
def imul_text(word,constant,m,inverse=False):
 ops=map_ops([m.gmul(constant,1<<i) for i in range(12)])
 if inverse:ops=reversed(ops)
 return ''.join(f'{op.upper()} q{word[i]} q{word[j]}\n' for op,i,j in ops)

def build(N,reverse=False):
 begin=time.time();n=N//2;m,k,fw,bk,tr=setup();nodes,kap,P,maps=node_maps(n);cb=km.CircuitBuilder();S=[cb.create_quantum_register(12,f'S{i}') for i in range(N)];G=cb.create_quantum_register(12,'g')
 headers='\n'.join(line for line in str(cb.finish_circuit()).splitlines() if line.startswith(('REGISTER','APPEND_TO_REGISTER')))+'\n'
 data=[list(range(24*i,24*i+24)) for i in range(n)];g=list(range(12*N,12*N+12));scratch=list(range(12*N+12,12*N+12+73))
 inv=inverse24();invbody=body(inv);ops=linear_map(N)
 path=Path(f'candidates/schur_extract_n{N}_{"inverse" if reverse else "forward"}.kmx')
 with path.open('w') as f:
  f.write(headers)
  if not reverse:
   for op,a,b in ops:f.write(f'{op.upper()} q{a} q{b}\n')
  for i in (reversed(range(n)) if reverse else range(n)):
   cur=data[i];node_i=tr(nodes[i]&4095,fw)
   pc=pivot(node_i,reverse,first=i==0);pb=body(pc);prev=data[i-1] if i else cur
   pmap={**{j:cur[j] for j in range(24)},**{24+j:g[j] for j in range(12)},**{36+j:prev[j] for j in range(24)},**{60+j:scratch[j] for j in range(pc.num_qubits-60)}}
   if reverse:f.write(mapped(pb,pmap))
   for j in (reversed(range(i+1,n)) if reverse else range(i+1,n)):
    target=data[j];delta=tr((nodes[i]^nodes[j])&4095,fw);constant=tr(kap[i]^kap[j],fw)
    def translate():
     f.write(''.join(f'CX q{a} q{b}\n' for a,b in zip(cur,target)))
     f.write(axpy_text(cur[12:],target[:12],delta,m))
    if not reverse:translate()
    if reverse:f.write(imul_text(target[:12],constant,m,True));f.write(imul_text(target[12:],constant,m,True))
    qmap={**dict(enumerate(target)),**{24+x:scratch[x] for x in range(inv.num_qubits-24)}};f.write(mapped(invbody,qmap))
    if not reverse:f.write(imul_text(target[:12],constant,m));f.write(imul_text(target[12:],constant,m))
    if reverse:translate()
   if not reverse:f.write(mapped(pb,pmap))
  if reverse:
   for op,a,b in reversed(ops):f.write(f'{op.upper()} q{a} q{b}\n')
 c=km.Circuit.from_file(str(path),format='kmx');c.to_file(str(path.with_suffix('.kmb')),format='kmb')
 report=dict(N=N,reverse=reverse,Q=c.num_qubits,T=c.operation_statistics().num_toffoli_like,seconds=time.time()-begin,scope='Schur pivot extraction only; synthesis, phase, and chart repair excluded')
 Path(f'results/schur_extract_n{N}_{"inverse" if reverse else "forward"}_build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
 return c

def model(s):
 n=len(s)//2;nodes,kap,P,maps=node_maps(n);v=transform(s,maps);g=1;A=B=0;out=[]
 for i in range(n):
  b=v[i]>>12;a=(v[i]&4095)^F.mul(nodes[i]&4095,b)
  for j in range(i+1,n):
   den=v[j]^a^((F.mul(nodes[j]&4095,b))|(b<<12))
   if den:
    from .quadratic_schur_model import einv,bmul
    v[j]=bmul(einv(den),kap[i]^kap[j])
   else:v[j]=0
  aa=F.mul(g,a)^A;bb=F.mul(g,b)^B;out.extend([aa,bb]);g=F.mul(F.mul(bb or 1,bb or 1),F.inv(g));A=aa^bb;B=bb
 return out,g

