# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""A source-resident three-field endpoint with monic final cofactor gauge."""
import argparse,json
from pathlib import Path
import numpy as np
import kickmix as km
from .extension_inverse import Adapter,setup
from .fast_dqi import FastBuilder
from .lean_emitter import create
from .cubic_low_workspace_inverse_compact import bind
from .raw_three_jet_step import build as jet_step
from .raw_three_jet_model import endpoint
from .raw_cf_model import extract
from .quadratic_schur_model import F
from .schur_extract import body,mapped


def boundary(inverse=False):
 m=setup()[0];m.inv_word=bind(m);b=FastBuilder(km.CircuitBuilder());D=b.create_quantum_register(12,'d');P=b.create_quantum_register(12,'p');Q=b.create_quantum_register(12,'q');ab=Adapter(b);sc,E=create(m,ab);d=[q.id for q in D];q=[v.id for v in Q];z=b.alloc_qubits(1)[0]
 def detect():
  with m.eq_test(E,q,0) as zero:E.cx(zero,z.id)
 detect()
 if inverse:b.cswap(z,D,P)
 b.cx(z,Q[0])
 with m.inv_word(E,q) as qi,m.opened(E,'three_jet_boundary_product',12) as tmp:m.mon_slot(E,d,q if inverse else qi,qi if inverse else q,tmp)
 b.cx(z,Q[0])
 if not inverse:b.cswap(z,D,P)
 detect();b.free(km.array([z]));ab.release_recycle('three_boundary_emitter',sc);c=b.finish_circuit();return km.Circuit(str(c)+'\n'+''.join(f'BIT_STORE0 b{i}\n' for i in range(c.num_bits)))


def build(N,inverse=False):
 n=N//2;b=km.CircuitBuilder()
 for i in range(N):b.create_quantum_register(12,f'S{i}')
 tail=[list(range(12)),list(range(12*N,12*N+12)),list(range(12,24))];headers=str(b.finish_circuit())+'\n'+''.join(''.join(f'APPEND_TO_REGISTER q{q} r{N+i}\n' for q in w)+f'REGISTER r{N+i} "{name}"\n' for i,(name,w) in enumerate(zip(['tailN0','tailN1','tailB0'],tail)));out=[headers];pool=list(range(12*N+12,12*N+160))
 def gate(op,*qs):out.append(op+' '+ ' '.join(f'q{q}' for q in qs)+'\n')
 def emit(c,ports):
  qm={q.id:v for name,w in ports.items() for q,v in zip(c.register_data[name],w)};qm.update(dict(zip([q for q in range(c.num_qubits) if q not in qm],pool)));out.append(mapped(body(c),qm))
 base=dict(d=tail[0],p=tail[1],q=tail[2])
 if inverse:emit(boundary(True),base)
 else:
  for q,r in zip(tail[2],tail[0]):gate('CX',q,r)
  gate('X',tail[1][0])
 c=jet_step(inverse)
 for i in (reversed(range(1,n)) if inverse else range(1,n)):emit(c,dict(a=list(range(24*i,24*i+12)),b=list(range(24*i+12,24*i+24)),**base))
 if inverse:
  gate('X',tail[1][0])
  for q,r in zip(tail[2],tail[0]):gate('CX',q,r)
 else:emit(boundary(),base)
 return km.Circuit(''.join(out))


