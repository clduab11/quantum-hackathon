# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Raw fixed-node Schur extraction without scalar normalization or swaps."""
import argparse,json,time
from pathlib import Path
import numpy as np
import kickmix as km
from .extension_inverse import setup
from .schur_extract import body,mapped,BRE,linear_map,imul_text,axpy_text
from .spooky_extension_compact_phase import build as inverse
from .quadratic_schur_model import node_maps
from .raw_cf_model import extract


def build(N,reverse=False):
 start=time.time();n=N//2;m,k,fw,bk,tr=setup();nodes,kap,_,_=node_maps(n);cb=km.CircuitBuilder()
 for i in range(N):cb.create_quantum_register(12,f'S{i}')
 total=24*n*(n-1)//2;cb.create_classical_register(total,'ghost');heads=str(cb.finish_circuit())+'\n';data=[list(range(24*i,24*i+24)) for i in range(n)];scratch=list(range(12*N,12*N+80));c=inverse(reverse);txt=body(c);ops=linear_map(N);path=Path(f'candidates/schur_extract_raw_compact_n{N}_{"inverse" if reverse else "forward"}.kmx');pair={(i,j):sum(n-1-z for z in range(i))+j-i-1 for i in range(n) for j in range(i+1,n)}
 with path.open('w') as f:
  f.write(heads)
  if not reverse:
   for op,a,b in ops:f.write(f'{op.upper()} q{a} q{b}\n')
  for i in (reversed(range(n)) if reverse else range(n)):
   cur=data[i]
   if reverse:f.write(axpy_text(cur[12:],cur[:12],tr(nodes[i]&4095,fw),m))
   for j in (reversed(range(i+1,n)) if reverse else range(i+1,n)):
    target=data[j];constant=tr(kap[i]^kap[j],fw)
    def translate():
     for q,r in zip(cur,target):f.write(f'CX q{q} q{r}\n')
     f.write(axpy_text(cur[12:],target[:12],tr((nodes[i]^nodes[j])&4095,fw),m))
    def scale(back=False):
     for w in [target[:12],target[12:]]:f.write(imul_text(w,constant,m,back))
    if reverse:scale(True)
    else:translate()
    qm=dict(enumerate(target));qm.update({24+j:q for j,q in enumerate(scratch[:c.num_qubits-24])});base=24*pair[i,j];f.write(BRE.sub(lambda x:f'b{base+int(x[1]) if int(x[1])<24 else total+int(x[1])-24}',mapped(txt,qm)))
    if reverse:translate()
    else:scale()
   if not reverse:f.write(axpy_text(cur[12:],cur[:12],tr(nodes[i]&4095,fw),m))
  if reverse:
   for op,a,b in reversed(ops):f.write(f'{op.upper()} q{a} q{b}\n')
 c=km.Circuit.from_file(str(path),format='kmx');c.to_file(str(path.with_suffix('.kmb')),format='kmb');r=dict(N=N,reverse=reverse,Q=c.num_qubits,T=c.operation_statistics().num_toffoli_like,seconds=time.time()-start);Path(f'results/schur_extract_raw_compact_n{N}_{"inverse" if reverse else "forward"}_build.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True);return c


