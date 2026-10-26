# SPDX-License-Identifier: Apache-2.0
"""PRA-246 port of ViberTeam v2 methods; attribution and changes in FIT_V4.md."""
from __future__ import annotations
import math, json
import numpy as np
from scipy.linalg import qr, solve_triangular
from scipy.optimize import minimize

def qr_model(u,w,h):
 r,b,c=w.shape;i,j=np.tril_indices(u.shape[-1]);s=np.where(i==j,1.,np.sqrt(2.))
 q=[];t=[]
 for ur in u:
  ur=ur/np.linalg.norm(ur,axis=1,keepdims=True)
  qq,tt=qr((ur[:,i]*ur[:,j]*s).T,mode='economic',check_finite=False);q.append(qq);t.append(tt)
 qa=np.concatenate(q,axis=1);cross=(qa.T@qa).reshape(r,b,r,b).transpose(0,2,1,3)
 t=np.asarray(t);v=t@w;k0=v@v.swapaxes(1,2)
 x=np.concatenate([qq@vv for qq,vv in zip(q,v)],axis=1);res=x@x.T-h
 e0=float(np.sum(res*res));eq=res@qa
 er=np.stack([q[rho].T@eq[:,rho*b:(rho+1)*b] for rho in range(r)])
 er=(er+er.swapaxes(1,2))*.5
 def project(k):return np.sum((cross@k[None,:,:,:])@cross.swapaxes(2,3),axis=1)
 def quantities(vv):
  delta=vv@vv.swapaxes(1,2)-k0;dm=project(delta)
  e=e0+2*float(np.sum(er*delta))+float(np.sum(delta*dm))
  return e,4*(er+dm)@vv
 def to_w(vv):return np.stack([solve_triangular(tr,vr,lower=False,check_finite=False) for tr,vr in zip(t,vv)])
 def grad_to_v(g):return np.stack([solve_triangular(tr.T,gr,lower=True,check_finite=False) for tr,gr in zip(t,g)])
 return v,quantities,to_w,grad_to_v


def fixed_word_fit(u,w,h,*,maxiter=400,target=.018):
 v,quant,to_w,_=qr_model(u,w,h);shape=v.shape;best=(math.inf,v.copy());history=[];calls=0
 def objective(flat):
  nonlocal best,calls
  calls+=1;vv=flat.reshape(shape);e,g=quant(vv)
  if e<best[0]:best=e,vv.copy()
  if calls%50==0:
   row=dict(stage='fixed_word_weights',call=calls,E2=math.sqrt(max(e,0)));history.append(row);print(json.dumps(row),flush=True)
  return 1000*e,1000*g.ravel()
 opt=minimize(objective,v.ravel(),jac=True,method='L-BFGS-B',options=dict(maxiter=maxiter,maxcor=15,ftol=1e-14,gtol=1e-8,maxls=30))
 wnew=to_w(best[1])
 return wnew,dict(before_E2=math.sqrt(quant(v)[0]),after_E2=math.sqrt(max(best[0],0)),calls=calls,iterations=int(opt.nit),success=bool(opt.success),history=history)


def joint_norm(context,data,brot=10,*,maxiter=100,stages=3):
 from . import native as C, words as F
 u=F.restore_factor(data,brot)['U'];u/=np.linalg.norm(u,axis=-1,keepdims=True)
 h=C.packed_target(context,data)
 v0,err,to_w,gradient_to_v=qr_model(u,data['W'],h)
 w0,a0,shift,beta=C.native_inputs(context,data);r,b,c=v0.shape;cut=v0.size
 const=context.reference['h1_thc']-.5*context.reference['electrons']*shift+beta*np.eye(76)
 energy=context.energy_upper-context.reference['ecore']+context.reference['electrons']*beta
 cap=.019999**2;gf=3.915048;lf=49.001;best=None;bestnorm=math.inf;calls=0;history=[]
 def quantities(z):
  v=z[:cut].reshape(r,b,c);a=z[cut:].reshape(r,c);w=to_w(v);e,ge=err(v)
  combined=np.einsum('rbc,rc->rb',w,a)
  h1=const-np.einsum('rb,rbp,rbq->pq',combined,u,u,optimize=True)
  val,vec=np.linalg.eigh(h1);l1=float(np.abs(val).sum());sign=(vec*np.sign(val))@vec.T
  q=np.einsum('rbp,pq,rbq->rb',u,sign,u,optimize=True)
  hw=a+w.sum(axis=1);total=np.abs(w).sum(axis=1)+np.abs(hw)
  gap=energy+l1-float(val.sum())+.5*float(np.sum(a*a));lam=l1+.25*float(np.sum(total*total))
  gwg=(1-q)[:,:,None]*a[:,None,:];gag=a+np.einsum('rb,rbc->rc',1-q,w)
  gwl=-q[:,:,None]*a[:,None,:]+.5*total[:,None,:]*(np.sign(w)+np.sign(hw)[:,None,:])
  gal=-np.einsum('rb,rbc->rc',q,w)+.5*total*np.sign(hw)
  return e,gap,lam,np.r_[ge.ravel(),np.zeros(r*c)],np.r_[gradient_to_v(gwg).ravel(),gag.ravel()],np.r_[gradient_to_v(gwl).ravel(),gal.ravel()]
 z=np.r_[v0.ravel(),a0.ravel()]
 # Independent directional derivative check at a smooth generic point.
 test=z+.00031*np.cos(np.arange(z.size)*1.61803398875);d=np.sin(np.arange(z.size)+.5);d/=np.linalg.norm(d);dt=1e-7
 q=quantities(test);fd=(np.array(quantities(test+dt*d)[:3])-np.array(quantities(test-dt*d)[:3]))/(2*dt)
 an=np.array([q[k]@d for k in (3,4,5)])
 assert np.max(abs(fd-an))<3e-5,(fd,an)
 def objective(z,mu):
  nonlocal best,bestnorm,calls
  calls+=1;e,g,l,ge,gg,gl=quantities(z);rad=g*(2*l-g)
  if 0<=e<cap and g>3.914898 and l>49 and rad>0:
   norm=math.sqrt(rad)
   if norm<bestnorm:
    best=z.copy();bestnorm=norm;history.append(dict(call=calls,E2=math.sqrt(e),E_gap=g,Lambda=l,lambda_eff=norm))
  se=1-e/cap;sg=g-gf;sl=l-lf
  if rad<=0 or se<=0 or sg<=0 or sl<=0:
   ve=max(0.,-se);vg=max(0.,-sg);vl=max(0.,-sl)
   return 1000+1e4*(ve*ve+vg*vg+vl*vl),2e4*(ve*ge/cap-vg*gg-vl*gl)
  value=.5*np.log(rad)-mu*(np.log(se)+np.log(sg)+np.log(sl))
  grad=((l-g)*gg+g*gl)/rad+mu*(ge/(cap*se)-gg/sg-gl/sl)
  return float(value),grad
 initial=quantities(z)
 if initial[0]>=cap:return data,dict(status='INITIAL_E2_OUTSIDE_JOINT_BARRIER',E2=math.sqrt(initial[0]))
 for mu in (1e-3,1e-4,1e-5,1e-6)[:stages]:
  opt=minimize(lambda zz:objective(zz,mu),z,jac=True,method='L-BFGS-B',options=dict(maxiter=maxiter,maxcor=12,maxls=30,ftol=1e-12,gtol=1e-8));z=opt.x
 if best is None:return data,dict(status='NO_JOINT_FEASIBLE_CHECKPOINT',calls=calls)
 result={k:np.array(v,copy=True) for k,v in data.items()};w=to_w(best[:cut].reshape(r,b,c));a=best[cut:].reshape(r,c)
 result['W']=w;result['H2_I']=a+w.sum(axis=1);result=C.refresh_one_body(context,F.restore_factor(result,brot),brot)
 return result,dict(status='JOINT_NUMERICAL_SEARCH_FULL_QUANTUM_PENDING',calls=calls,best_lambda_eff=bestnorm,history=history,
    derivative_fixture=dict(finite=fd.tolist(),analytic=an.tolist(),max_abs_error=float(np.max(abs(fd-an)))))

