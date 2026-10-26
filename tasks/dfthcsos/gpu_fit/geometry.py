# SPDX-License-Identifier: Apache-2.0
"""PRA-246 port of ViberTeam v2 methods; attribution and changes in FIT_V4.md."""
from __future__ import annotations
import numpy as np

def projectors(u):
 u=np.asarray(u,dtype=np.float64);u=u/np.linalg.norm(u,axis=-1,keepdims=True)
 i,j=np.tril_indices(u.shape[-1]);s=np.where(i==j,1.,np.sqrt(2.))
 return (u[:,:,i]*u[:,:,j]*s).transpose(0,2,1)


def columns(u,w):
 p=projectors(u);x=p@w
 return x.transpose(1,0,2).reshape(p.shape[1],-1)


def physical_error(u,w,h):
 x=columns(u,w)
 return float(np.linalg.norm(x@x.T-h))

