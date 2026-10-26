# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Mask-selected parity of flag * numerator / divisor, without a quotient word.

A runtime classical mask scales the divisor through reversible row operations.
The tower inverse-dot circuit then gates its final three-bit pairing by flag.
"""
import json
from pathlib import Path
import numpy as np
import kickmix as km
from .cubic_mask_phase_joint import classical_scale_inverse
from .cubic_trace_field import data
from .extension_inverse import setup
from .recursive_forney import inverse_dot_data
from .tower_inverse import map_ops,apply_map
from .fast_dqi import FastBuilder


def apply(b,divisor,numerator,flag,mask):
 m,k,fw,bk,tr=setup();field=km.GF2Field(12)
 source=km.array([km.q(q) for q in divisor]);num=km.array([km.q(q) for q in numerator]);bops=map_ops(bk)
 trans=tuple(sum(((fw[i]>>j)&1)<<i for i in range(12)) for j in range(12));mops=map_ops(trans)
 def trace(v):
  ans=0
  for _ in range(12):ans^=v;v=field.mul(v,v)
  assert ans in (0,1);return ans
 gram=map_ops([sum(trace(field.mul(1<<i,1<<j))<<i for i in range(12)) for j in range(12)])
 active=b.alloc_bits(1)[0];b.bit_store(active,False);b.bit_store(active,True,control=mask);b.push_condition(active)
 apply_map(b,source,bops);apply_map(b,num,bops);apply_map(b,mask,mops)
 dual=map_ops(data()['dual_columns']);apply_map(b,mask,dual);record=classical_scale_inverse(b,source,mask);apply_map(b,num,gram)
 leaf,iv,cleanup=inverse_dot_data(b,source,num)
 for q,r in zip(leaf,iv):b.ccz(km.q(flag),q,r)
 cleanup();apply_map(b,num,gram,True)
 for kind,j,i,bit in reversed(record):
  b.push_condition(bit);getattr(b,kind)(source[j],source[i]);b.pop_condition();b.bit_store(bit,False);b.free(km.array([bit]))
 apply_map(b,mask,dual,True);apply_map(b,mask,mops,True);apply_map(b,num,bops,True);apply_map(b,source,bops,True)
 b.pop_condition();b.bit_store(active,False);b.free(km.array([active]))


