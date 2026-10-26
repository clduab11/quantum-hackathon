# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Reversible three-field infinity jet, without affine reciprocal steps."""
import argparse,json
from pathlib import Path
import numpy as np
import kickmix as km
from .extension_inverse import Adapter,setup
from .fast_dqi import FastBuilder
from .lean_emitter import create
from .tower_inverse import map_ops,apply_map


def build(inverse=False):
 m=setup()[0];b=FastBuilder(km.CircuitBuilder());regs={name:b.create_quantum_register(12,name) for name in ['a','b','p','q','d']};ab=Adapter(b);sc,E=create(m,ab);w={k:[q.id for q in v] for k,v in regs.items()};sq=map_ops([m.gmul(1<<i,1<<i) for i in range(12)])
 def swap():b.swap(regs['p'],regs['q'])
 def top():E.mac(m.prod_rt(w['p'],w['b'],w['q']))
 def deriv():
  E.mac(m.prod_rt(w['d'],w['q'],w['p']));apply_map(b,regs['q'],sq);E.mac(m.prod_rt(w['d'],w['a'],w['q']));apply_map(b,regs['q'],sq,True)
 if inverse:swap();deriv();top()
 else:top();deriv();swap()
 ab.release_recycle('three_jet_emitter',sc);c=b.finish_circuit();return km.Circuit(str(c)+'\n'+''.join(f'BIT_STORE0 b{i}\n' for i in range(c.num_bits)))


