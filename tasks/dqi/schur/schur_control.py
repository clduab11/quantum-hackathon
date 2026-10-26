# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Twelve-AND controlled field-linear maps with measured input erasure."""
import json
from pathlib import Path
import numpy as np
import kickmix as km
from .extension_inverse import Adapter,setup
from .fast_dqi import FastBuilder


def caxpy_rt(m,control,source,target,c):
 rt=[]
 for i,q in enumerate(source):
  v=m.gmul(c,1<<i);dest=[target[j] for j in range(12) if v>>j&1]
  if dest:rt.append(('P',(control,),0,(q,),0,tuple(dest)))
 return rt


def caxpy(m,E,control,source,target,c):E.mac(caxpy_rt(m,control,source,target,c))


def cimul(m,E,control,word,c,inverse=False):
 if c==1:return
 if inverse:c=m.ginv(c)
 with m.opened(E,'controlled_constant_output',12) as out:
  rt=[('L',(q,),0,(t,)) for q,t in zip(word,out)]+caxpy_rt(m,control,word,out,c^1);E.mac(rt)
  undo=[('L',(q,),0,(t,)) for q,t in zip(out,word)]+caxpy_rt(m,control,out,word,m.ginv(c)^1);E.free(undo)
  for a,b in zip(word,out):E.b.swap(a,b)


