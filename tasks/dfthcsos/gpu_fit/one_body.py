# SPDX-License-Identifier: Apache-2.0
"""PRA-246 port of ViberTeam v2 methods; attribution and changes in FIT_V4.md."""
from __future__ import annotations
import time, json
import numpy as np
from scipy.optimize import linear_sum_assignment

def polish(context,data,brot,*,target=.0195,max_steps=2000,seconds=90):
 from . import native as C
 from .integer import decode_numpy
 result={k:np.array(v,copy=True) for k,v in data.items()};words=result['angle_words'][:76].copy();edges=result['tree_edges']
 w,a,shift,beta=C.native_inputs(context,result);_,u=C.decoded_vectors(context,result,brot)
 comb=np.einsum('rc,rbc->rb',a,w)
 h=context.reference['h1_thc']-.5*context.reference['electrons']*shift+beta*np.eye(76)-np.einsum('rb,rbp,rbq->pq',comb,u,u,optimize=True)
 val,vec=np.linalg.eigh(h);v=decode_numpy(words,edges,brot=brot);v/=np.linalg.norm(v,axis=1,keepdims=True)
 ii,jj=linear_sum_assignment(-abs(v@vec));lam=np.empty(76);lam[ii]=val[jj]
 e=np.einsum('j,jp,jq->pq',lam,v,v,optimize=True)-h;initial=float(np.linalg.norm(e))
 rowid=np.repeat(np.arange(76),150);angle=np.tile(np.repeat(np.arange(75),2),76);direction=np.tile([-1,1],76*75)
 candidates=np.repeat(words,150,axis=0);candidates[np.arange(len(candidates)),angle]=(candidates[np.arange(len(candidates)),angle]+direction)%(1<<brot)
 cv=decode_numpy(candidates,edges,brot=brot);cv/=np.linalg.norm(cv,axis=1,keepdims=True)
 start=time.monotonic();history=[];accepted=0
 for step in range(max_steps):
  current=float(np.sum(e*e))
  if current<=target*target or time.monotonic()-start>=seconds:break
  old=np.einsum('jp,pq,jq->j',v,e,v,optimize=True)
  new=np.sum((cv@e)*cv,axis=1);overlap=np.sum(cv*v[rowid],axis=1)
  change=2*lam[rowid]*(new-old[rowid])+2*lam[rowid]**2*(1-overlap*overlap)
  k=int(np.argmin(change));delta=float(change[k])
  if delta>=-1e-15:break
  r=int(rowid[k]);vnew=cv[k].copy();vold=v[r].copy()
  e+=lam[r]*(np.outer(vnew,vnew)-np.outer(vold,vold));v[r]=vnew;words[r]=candidates[k]
  idx=slice(r*150,(r+1)*150);candidates[idx]=words[r]
  rr=np.arange(r*150,(r+1)*150);candidates[rr,angle[rr]]=(candidates[rr,angle[rr]]+direction[rr])%(1<<brot)
  cv[idx]=decode_numpy(candidates[idx],edges,brot=brot);cv[idx]/=np.linalg.norm(cv[idx],axis=1,keepdims=True)
  accepted+=1
  if accepted%100==0:history.append(dict(accepted=accepted,E1=float(np.linalg.norm(e)),seconds=time.monotonic()-start))
 result['angle_words'][:76]=words
 metrics=C.evaluate_words(context,result,brot)
 final=float(np.linalg.norm(e));assert abs(metrics['error_1']-final)<1e-10,(metrics['error_1'],final)
 report=dict(status='EXACT_ONE_BODY_GRID_POLISH_NOT_FULL_PASS',brot=brot,initial_E1=initial,final_E1=final,accepted=accepted,
   seconds=time.monotonic()-start,metrics=metrics,history=history)
 print(json.dumps({k:v for k,v in report.items() if k!='history'}),flush=True)
 return result,report

