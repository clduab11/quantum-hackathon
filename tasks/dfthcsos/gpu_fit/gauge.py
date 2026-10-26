# SPDX-License-Identifier: Apache-2.0
"""PRA-246 port of ViberTeam v2 methods; attribution and changes in FIT_V4.md."""
from __future__ import annotations
import time
import numpy as np

def prox_squared_l1(B,tau):
    """Exact columnwise prox of tau*||column||_1**2."""
    n=B.shape[1]
    values=np.sort(np.abs(B),axis=1)[:,::-1]
    prefix=np.cumsum(values,axis=1)
    counts=np.arange(1,n+1)[None,:,None]
    thresholds=2*tau*prefix/(1+2*tau*counts)
    active=np.sum(values>thresholds,axis=1)
    level=np.take_along_axis(thresholds,np.maximum(active-1,0)[:,None,:],axis=1)
    return np.sign(B)*np.maximum(np.abs(B)-level,0)

def deterministic_column_gauge(data, *, plane_sweeps=12):
    """The earlier bounded search with every wallclock stop removed.

    There are five60-step proximal stages, two40-step Cayley stages
    (each line search at most9 trials), and at most12 complete plane sweeps.
    All acceptance comparisons use the actual nonsmoothed L1 objective.
    """
    started=time.monotonic()
    A=np.concatenate([data['W'],np.asarray(data['H2_I'])[:,None]],axis=1)
    R,N,K=A.shape
    cost=lambda B:np.sum(np.sum(np.abs(B),axis=1)**2,axis=1)
    initial=cost(A)
    best=A.copy();values=initial.copy()
    identity=np.broadcast_to(np.eye(K),(R,K,K)).copy()
    q=identity.copy();bestq=identity.copy()
    history=[]

    def keep(B,Q,label):
        nonlocal best,bestq,values
        current=cost(B)
        take=current<values-1e-12
        best[take]=B[take];bestq[take]=Q[take];values[take]=current[take]
        if label:
            history.append(dict(stage=label,l1_square=float(values.sum())))

    for tau in (.03,.01,.003,.001,.0003):
        for _ in range(60):
            target=prox_squared_l1(A@q,tau)
            left,_,right=np.linalg.svd(np.swapaxes(A,1,2)@target,full_matrices=False)
            q=left@right
            keep(A@q,q,None)
        keep(A@q,q,f'proximal_procrustes_tau{tau}')
    q=bestq.copy()
    positive=np.abs(A[A!=0])
    for relative in (.003,.0003):
        eps=max((float(np.median(positive)) if positive.size else 1.)*relative,1e-9)
        for _ in range(40):
            B=A@q;roots=np.sqrt(B*B+eps*eps);l1=roots.sum(axis=1)
            grad=np.swapaxes(A,1,2)@(2*B/roots*l1[:,None,:])
            local=np.swapaxes(q,1,2)@grad
            skew=local-np.swapaxes(local,1,2)
            step=.08/np.maximum(np.linalg.norm(skew,axis=(1,2)),1e-12)
            old=np.sum(l1*l1,axis=1);accepted=np.zeros(R,dtype=bool);nq=q.copy()
            for _ in range(9):
                S=.5*step[:,None,None]*skew
                trial=q@np.linalg.solve(identity+S,identity-S)
                trial_roots=np.sqrt((A@trial)**2+eps*eps)
                trial_loss=np.sum(trial_roots.sum(axis=1)**2,axis=1)
                take=(~accepted)&(trial_loss<old)
                nq[take]=trial[take];accepted|=take
                if accepted.all():break
                step[~accepted]*=.25
            q=nq;keep(A@q,q,None)
        keep(A@q,q,f'smoothed_cayley_eps{relative}')
    for sweep in range(plane_sweeps):
        accepted=0
        for i in range(K):
            for j in range(i+1,K):
                x,y=best[:,:,i].copy(),best[:,:,j].copy()
                theta=np.mod(np.arctan2(y,x),np.pi/2)
                theta=np.concatenate([np.zeros((R,1)),theta],axis=1)
                co,si=np.cos(theta)[:,:,None],np.sin(theta)[:,:,None]
                losses=(np.abs(co*x[:,None]+si*y[:,None]).sum(axis=2)**2+
                        np.abs(co*y[:,None]-si*x[:,None]).sum(axis=2)**2)
                idx=np.argmin(losses,axis=1)
                old=np.abs(x).sum(axis=1)**2+np.abs(y).sum(axis=1)**2
                angle=np.where(losses[np.arange(R),idx]<old-1e-12,theta[np.arange(R),idx],0)
                accepted+=int(np.count_nonzero(angle))
                co,si=np.cos(angle)[:,None],np.sin(angle)[:,None]
                best[:,:,i],best[:,:,j]=co*x+si*y,co*y-si*x
        history.append(dict(stage=f'exact_plane_sweep{sweep}',
                            l1_square=float(cost(best).sum()),accepted_rotations=accepted))
        if not accepted:break
    drift=float(np.max(np.abs(best@np.swapaxes(best,1,2)-A@np.swapaxes(A,1,2))))
    if drift>1e-9:raise ArithmeticError(f'Augmented Gram drift {drift}')
    if float(cost(best).sum())>float(initial.sum())+1e-9:
        raise ArithmeticError('Original exact gauge objective increased')
    result={key:np.array(value,copy=True) for key,value in data.items()}
    result['W'],result['H2_I']=best[:,:-1],best[:,-1]
    return result,dict(method='deterministic proximal Procrustes + Cayley + exact planes',
                       wall_seconds=time.monotonic()-started,
                       time_dependent_stopping=False,
                       iteration_limits=dict(proximal_stages=5,proximal_steps=60,
                                             cayley_stages=2,cayley_steps=40,line_search=9,
                                             plane_sweeps=plane_sweeps),
                       augmented_Gram_max_drift=drift,old_l1_square=float(initial.sum()),
                       new_l1_square=float(cost(best).sum()),history=history)

