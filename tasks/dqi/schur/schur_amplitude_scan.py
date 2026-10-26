# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Eleven-Toffoli root-gated scan of a direct amplitude polynomial."""
from functools import lru_cache
from types import SimpleNamespace
import json
from pathlib import Path
import numpy as np
import kickmix as km
from .extension_inverse import setup
from .schur_extract import body,mapped,BRE,imul_text
from .tower_inverse import map_ops
from .quadratic_schur_model import F,node_maps
from .fast_dqi import FastBuilder


@lru_cache(None)
def phase_template():
 b=FastBuilder(km.CircuitBuilder());s=b.create_quantum_register(12,'s');w=b.create_quantum_register(12,'w');mask=b.create_classical_register(12,'mask');lad=b.alloc_qubits(11);b.x(s);b.init_and(s[0],s[1],lad[0])
 for i in range(1,11):b.init_and(lad[i-1],s[i+1],lad[i])
 for bit,q in zip(mask,w):b.push_condition(bit);b.cz(lad[-1],q);b.pop_condition()
 for i in reversed(range(1,11)):b.del_and(lad[i-1],s[i+1],lad[i])
 b.del_and(s[0],s[1],lad[0]);b.x(s);b.free(lad);c=b.finish_circuit();return km.Circuit(str(c)+'\n'+''.join(f'BIT_STORE0 b{i}\n' for i in range(12,c.num_bits)))


def write_scan(f,N,M,private_base,banks,private_qubits):
 m,_,fw,bk,tr=setup();nn,bb=banks;n=N//2;gf=km.GF2Field(12);_,_,P,_=node_maps(n);linearfield=SimpleNamespace(gmul=gf.mul);templ=phase_template();scratch=private_qubits[:templ.num_qubits-24];assert len(scratch)==templ.num_qubits-24 and not(set(scratch)&{q for w in nn+bb for q in w});qmap={**dict(enumerate(bb[0]+nn[0])),**{24+i:q for i,q in enumerate(scratch)}};kernel=mapped(body(templ),qmap)
 def cmap(word,ops):
  for op,a,b in ops:f.write(f'{op.upper()} q{word[a]} q{word[b]}\n')
 for word in nn+bb:cmap(word,map_ops(bk))
 a=1;alpha=int(gf.primitive_element)
 for j in range(M):
  top=int(gf.pow(a,n));p=F.evaluate(P,a);factor=gf.pow(gf.mul(a,p),4094);cols=[gf.mul(factor,1<<i) for i in range(12)];trans=tuple(sum(((cols[i]>>b)&1)<<i for i in range(12)) for b in range(12));ops=map_ops(trans)
  def evals(back=False):
   lines=[]
   for word in bb[1:]:lines.extend(f'CX q{x} q{y}\n' for x,y in zip(word,bb[0]))
   lines.extend(f'X q{bb[0][bit]}\n' for bit in range(12) if top>>bit&1)
   for word in nn[1:]:lines.extend(f'CX q{x} q{y}\n' for x,y in zip(word,nn[0]))
   f.write(''.join(reversed(lines) if back else lines))
  def cm(back=False):
   for op,x,y in (reversed(ops) if back else ops):
    for x,y in ([(x,y)] if op=='cx' else [(x,y),(y,x),(x,y)]):f.write(f'BIT_INVERT b{12*j+y} if b{12*j+x}\n')
  evals();cm();f.write(BRE.sub(lambda x:f'b{12*j+int(x[1]) if int(x[1])<12 else private_base+int(x[1])-12}',kernel));cm(True);evals(True)
  if j+1<M:
   for bank in [nn,bb]:
    for d,word in enumerate(bank[1:],1):f.write(imul_text(word,gf.pow(alpha,d),linearfield))
   a=int(gf.mul(a,alpha))
 if M>1:
  for bank in [nn,bb]:
   for d,word in enumerate(bank[1:],1):f.write(imul_text(word,gf.pow(alpha,d*(M-1)%4095),linearfield,True))
 for word in nn+bb:cmap(word,reversed(map_ops(bk)))
 return dict(kernel_Q=templ.num_qubits,kernel_T=templ.operation_statistics().num_toffoli_like)


