# SPDX-License-Identifier: Apache-2.0
"""Validated independent truth/dirty-family audits, independent of the compiler."""
import numpy as np
import kickmix as km
from tasks.dfthcsos.full_xor.paired_anf import batch_deltas
from dfthcsos.scoreinfra.circuits import register_layout

def indices(x):
 out=[]
 while x:
  low=x&-x;out.append(low.bit_length()-1);x^=low
 return out

def independent_truth(plan):
 """Expand actual product controls with Boolean OR, then zeta-evaluate.

 Does not use Plan.evaluate, compiler matrix/rank/pure-product helpers, or
 its ANF routine. Direct equality on the complete valid prefix [0,A).
 """
 A=plan.addresses;coeff=[0]*A
 if plan.blocks is not None:
  vals=[0]*A
  for sub in plan.blocks:
   for a,v in enumerate(independent_truth(sub)):vals[a]^=v
  return vals
 for mask,fan in plan.pure.items():
  if mask<A:coeff[mask]^=int(fan)
 for p in plan.products:
  left=indices(p.left1)+[h<<plan.low_bits for h in indices(p.right2)]
  right=indices(p.left2)+[h<<plan.low_bits for h in indices(p.right1)]
  for l in left:
   for r in right:
    m=l|r
    if m<A:coeff[m]^=int(p.fanout)
 for b in range((A-1).bit_length()):
  for a in range(A):
   if a&(1<<b):coeff[a]^=coeff[a^(1<<b)]
 return coeff

def assert_independent(plan,delta):
 expected=[sum(int(x)<<(j*plan.brot) for j,x in enumerate(row)) for row in delta]
 assert independent_truth(plan)==expected
