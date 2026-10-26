# SPDX-License-Identifier: Apache-2.0
"""PRA-246 port of ViberTeam v2 methods; attribution and changes in FIT_V4.md."""
from __future__ import annotations
import numpy as np

class Geometry:
 def __init__(self,u,w,device='cuda',dtype='float64'):
  import torch
  self.torch=torch;self.device=device;self.dtype=getattr(torch,dtype)
  self.u=torch.as_tensor(u,dtype=self.dtype,device=device).clone();self.u/=torch.linalg.vector_norm(self.u,dim=-1,keepdim=True)
  self.w=torch.as_tensor(w,dtype=self.dtype,device=device).clone()
  self.R,self.B,self.N=u.shape;self.C=w.shape[2];self.nu=self.u.numel()
  i,j=np.tril_indices(self.N);self.D=len(i)
  self.i=torch.as_tensor(i,device=device);self.j=torch.as_tensor(j,device=device)
  self.s=torch.as_tensor(np.where(i==j,1.,np.sqrt(2.)),dtype=self.dtype,device=device)
  self.refresh()
 def refresh(self):
  self.p=(self.u[:,:,self.i]*self.u[:,:,self.j]*self.s).transpose(1,2)
  self.x=(self.p@self.w).permute(1,0,2).reshape(self.D,-1)
  self.gram=self.x.T@self.x
 def tangent(self,du):return du-self.u*(du*self.u).sum(dim=-1,keepdim=True)
 def unpack(self,v):return self.tangent(v[:self.nu].reshape(self.u.shape)),v[self.nu:].reshape(self.w.shape)
 def flat(self,du,dw):return self.torch.cat((du.ravel(),dw.ravel()))
 def jvp(self,v):
  du,dw=self.unpack(v)
  dp=((du[:,:,self.i]*self.u[:,:,self.j]+self.u[:,:,self.i]*du[:,:,self.j])*self.s).transpose(1,2)
  return (dp@self.w+self.p@dw).permute(1,0,2).reshape(self.D,-1)
 def vjp(self,gx):
  t=self.torch;gr=gx.reshape(self.D,self.R,self.C).permute(1,0,2)
  gw=self.p.transpose(1,2)@gr;gp=(gr@self.w.transpose(1,2)).transpose(1,2)/self.s
  gm=t.zeros((self.R,self.B,self.N,self.N),device=self.device,dtype=self.dtype)
  gm[:,:,self.i,self.j]=gp;gm[:,:,self.j,self.i]=gp
  gu=2*(gm@self.u[:,:,:,None]).squeeze(-1)
  return self.flat(self.tangent(gu),gw)
 def normal(self,v):
  dx=self.jvp(v)
  return self.vjp(2*(dx@self.gram+self.x@(dx.T@self.x)))
 def diagonal(self):
  t=self.torch;g=t.diag(self.gram).reshape(self.R,self.C)
  ud=4*(self.w*self.w*g[:,None,:]).sum(dim=-1)
  wd=2*g[:,None,:].expand_as(self.w)
  return self.flat(ud[:,:,None].expand_as(self.u),wd).clamp_min(1e-9)
 def apply(self,step,alpha):
  du,dw=self.unpack(step);u=self.u+alpha*du
  u=u/self.torch.linalg.vector_norm(u,dim=-1,keepdim=True)
  return u,self.w+alpha*dw
 def trial_x(self,u,w):
  p=(u[:,:,self.i]*u[:,:,self.j]*self.s).transpose(1,2)
  return (p@w).permute(1,0,2).reshape(self.D,-1)


def pcg(g,b,diagonal,damping,iterations=60,tolerance=.05):
 t=g.torch;x=t.zeros_like(b);r=b.clone();z=r/((1+damping)*diagonal);p=z.clone();rz=r@z
 norm0=t.linalg.vector_norm(r);last=None
 for k in range(iterations):
  ap=g.normal(p)+damping*diagonal*p
  den=p@ap
  if float(den)<=0:break
  alpha=rz/den;x+=alpha*p;r-=alpha*ap
  last=float(t.linalg.vector_norm(r)/norm0)
  if last<tolerance:break
  z=r/((1+damping)*diagonal);rznew=r@z;p=z+(rznew/rz)*p;rz=rznew
 return x,dict(cg_iterations=k+1,cg_relative_residual=last)

