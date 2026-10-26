# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Overwrite A by A/B' modulo a squarefree monic odd-degree B.

Native implementation on the generic Euclidean E/O chart. It restores B and
has a literal inverse even on reversibly armed unsupported degree gaps.
"""
import argparse,json
from pathlib import Path
import numpy as np
import kickmix as km
from .extension_inverse import Adapter,setup
from .cubic_low_workspace_inverse import bind
from .tower_inverse import apply_map,map_ops
from .triangular_dp import DPArithmetic
from .bezout_payload_monic import apply as bezout_apply
from .fast_dqi import FastBuilder
from .lean_emitter import create as lean_create


def apply(m,E,A,B,one,inverse=False):
 n=len(A);assert n%2 and len(B)==n;t=n//2;b=E.b.raw;even=A[::2];odd=A[1::2];f=B[::2];g=B[1::2];math=DPArithmetic(m,E);rootops=map_ops([m.gpow(1<<i,2048) for i in range(12)])
 def root(back=False):
  for word in A+B:apply_map(b,km.array([km.q(q) for q in word]),rootops,back)
 def cross(first=True):
  for i in range(t):E.mac(m.prod_rt(even[i] if first else even[-1],g[i],even[-1] if first else even[i]))
 def bez(reverse=False):
  with m.opened(E,'derivative_gap_index',max(1,t.bit_length())) as index,m.opened(E,'derivative_gap_flag',1) as flag:bezout_apply(m,E,f,g,[even[:-1],odd],reverse,history=(index,flag[0]))
 def swap():
  for a,c in zip(even[:-1],odd):
   for q,r in zip(a,c):E.b.swap(q,r)
 def reverse():
  for i in range(n//2):
   for q,r in zip(A[i],A[-1-i]):E.b.swap(q,r)
 if inverse:
  reverse();math.triangular([one]+list(reversed(B[1:])),1,A,True);root();cross(False);swap();bez(True);cross();root(True)
 else:
  root();cross();bez();swap();cross(False);root(True);math.triangular([one]+list(reversed(B[1:])),1,A);reverse()


def build(n,inverse=False):
 m=setup()[0];m.inv_word=bind(m);b=FastBuilder(km.CircuitBuilder());aa=[b.create_quantum_register(12,f'A{i}') for i in range(n)];bb=[b.create_quantum_register(12,f'B{i}') for i in range(n)];ab=Adapter(b);sc,E=lean_create(m,ab);apply(m,E,[[q.id for q in w] for w in aa],[[q.id for q in w] for w in bb],[],inverse);ab.release_recycle('derivative_emitter',sc);c=b.finish_circuit();return km.Circuit(str(c)+'\n'+''.join(f'BIT_STORE0 b{i}\n' for i in range(c.num_bits)))


