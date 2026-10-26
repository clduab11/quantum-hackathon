# SPDX-License-Identifier: Apache-2.0
"""PRA-246 port of ViberTeam v2 methods; attribution and changes in FIT_V4.md."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, math, time
import numpy as np

def decode_numpy(words, edges, *, brot=10):
    """Sequential native word decoder; no root/tree-path shortcut required."""
    words = np.asarray(words, dtype=np.float64)
    edges = np.asarray(edges, dtype=np.int64)
    if words.ndim < 1 or edges.shape != (words.shape[-1], 2):
        raise ValueError("Expected one ordered edge per angle")
    n = len(edges) + 1
    if np.any(edges < 0) or np.any(edges >= n) or np.any(edges[:, 0] == edges[:, 1]):
        raise ValueError("Invalid rotation endpoints")
    u = np.zeros(words.shape[:-1] + (n,), dtype=np.float64)
    u[..., 0] = 1.
    for k, (p, q) in enumerate(edges):
        before_p, before_q = u[..., p].copy(), u[..., q].copy()
        theta = np.pi * (words[..., k] / (1 << (brot - 1)))
        c, s = np.cos(theta), np.sin(theta)
        u[..., p] = c * before_p - s * before_q
        u[..., q] = s * before_p + c * before_q
    return u


def angle_vjp_numpy(words, edges, vector_gradient, *, brot=10, return_mass=False):
    """Continuous word-unit VJP through normalized native Givens rotations.

    Used only to rank discrete proposals; it is not the derivative of the
    discontinuous integer objective. Zero sin/cos values need no division.
    """
    words = np.asarray(words, dtype=np.float64)
    edges = np.asarray(edges, dtype=np.int64)
    current = decode_numpy(words, edges, brot=brot)
    norm = np.linalg.norm(current, axis=-1, keepdims=True)
    unit = current / norm
    grad = np.asarray(vector_gradient, dtype=np.float64).copy()
    if grad.shape != current.shape:
        raise ValueError("Vector gradient shape disagrees with decoded words")
    grad = (grad - unit * np.sum(grad * unit, axis=-1, keepdims=True)) / norm
    result = np.zeros_like(words)
    mass = np.zeros_like(words) if return_mass else None
    step = np.pi / (1 << (brot - 1))
    for k in reversed(range(len(edges))):
        p, q = edges[k]
        after_p, after_q = current[..., p].copy(), current[..., q].copy()
        gp, gq = grad[..., p].copy(), grad[..., q].copy()
        if return_mass:
            mass[...,k]=(after_p*after_p+after_q*after_q)/(norm[...,0]*norm[...,0])
        result[..., k] = step * (-gp * after_q + gq * after_p)
        theta = np.pi * (words[..., k] / (1 << (brot - 1)))
        c, s = np.cos(theta), np.sin(theta)
        grad[..., p], grad[..., q] = c * gp + s * gq, -s * gp + c * gq
        current[..., p], current[..., q] = c * after_p + s * after_q, -s * after_p + c * after_q
    return (result,np.clip(mass,0.,1.)) if return_mass else result


def _sum(value, axis=None):
    if isinstance(value, np.ndarray):
        return np.sum(value, axis=axis)
    return value.sum() if axis is None else value.sum(dim=axis)


def exact_rank2_deltas(residual, d, v, g, *, symmetric_residual=False):
    """Exact algebraic delta for batches d/v shaped[D,M], scalar or[M]g.

    DeltaM=v*d.T+d*v.T+g*d*d.T. Its linear term is evaluated with a
    single fused matrix product E@(2v+g*d). Non-symmetric residuals are
    explicitly symmetrized unless the caller certifies the symmetric form.
    NumPy float64 and torch float64 tensors are accepted; no dtype downcast.
    """
    if str(residual.dtype) not in {'float64','torch.float64'}:
        raise ValueError("Exact physical candidate evaluation requires float64 residuals")
    if str(d.dtype) not in {'float64','torch.float64'} or str(v.dtype) not in {'float64','torch.float64'}:
        raise ValueError("Exact physical candidate evaluation requires float64 d/v")
    if not symmetric_residual:
        residual = (residual + residual.T) * .5
    if d.ndim == 1:
        d, v = d[:, None], v[:, None]
    if residual.ndim != 2 or residual.shape[0] != residual.shape[1] or d.shape != v.shape or d.shape[0] != residual.shape[0]:
        raise ValueError("Expected E[D,D],d[D,M],v[D,M]")
    dd, vv, dv = _sum(d * d, 0), _sum(v * v, 0), _sum(d * v, 0)
    linear = 2 * _sum(d * (residual @ (2 * v + d * g)), 0)
    return linear + 2 * vv * dd + 2 * dv * dv + 4 * g * dv * dd + g * g * dd * dd


@dataclass(frozen=True)
class CandidateEvaluation:
    state_version: int
    coordinates: np.ndarray  # [M,4]:rho,b,angle,direction(-1/+1)
    delta_loss: np.ndarray


class ExactAnglePolisher:
    def __init__(self, words_body, W, tree_edges, target_Hpacked, *, brot=10,
                 backend="numpy", device=None, decoder=None):
        if not 1 <= brot <= 16:
            raise ValueError("brot must lie in1..16")
        self.brot, self.modulus = int(brot), 1 << int(brot)
        self.edges = np.array(tree_edges, dtype=np.int64, copy=True)
        self.W = np.array(W, dtype=np.float64, copy=True)
        if self.W.ndim != 3 or min(self.W.shape) < 1 or not np.all(np.isfinite(self.W)):
            raise ValueError("Expected finite W[R,B,C]")
        self.W.flags.writeable = False
        self.R, self.B, self.C = self.W.shape
        self.K, self.N = len(self.edges), len(self.edges) + 1
        incoming = np.asarray(words_body)
        if (not np.issubdtype(incoming.dtype,np.integer) or np.any(incoming<0)
                or np.any(incoming>=self.modulus)):
            raise ValueError("All angle words, including optional one-body rows, must be legal unsigned integers")
        self._one_body = None
        if incoming.shape == (self.N + self.R * self.B, self.K):
            self._one_body = np.array(incoming[:self.N], dtype=np.uint16, copy=True)
            incoming = incoming[self.N:]
        if incoming.shape not in ((self.R, self.B, self.K), (self.R * self.B, self.K)):
            raise ValueError("words must be[R,B,K],[R*B,K], or full[N+R*B,K]")
        if (not np.issubdtype(incoming.dtype, np.integer) or
                np.any(incoming < 0) or np.any(incoming >= self.modulus)):
            raise ValueError("Words must be exact unsigned integers in the beta domain")
        self._words = np.array(incoming, dtype=np.int64, copy=True).reshape(self.R, self.B, self.K)
        self.decoder = decoder or (lambda w:decode_numpy(w, self.edges, brot=self.brot))
        self._U = self._decode(self._words)
        self.rows, self.cols = np.tril_indices(self.N)
        self.scale = np.where(self.rows == self.cols, 1., math.sqrt(2.))
        self.D = len(self.rows)
        self._torch = None
        if backend not in {"numpy", "torch"}:
            raise ValueError("backend must be numpy or torch")
        if backend == "torch":
            import torch
            self._torch = torch
            self.device = torch.device(device or "cpu")
        elif device not in (None, "cpu"):
            raise ValueError("Use backend='torch' for a GPU device")
        self.backend = backend
        packed = self._pack(self._U)
        self._X = self._array(np.einsum("rbd,rbc->rdc", packed, self.W, optimize=True))
        del packed
        target = self._array(target_Hpacked)
        if tuple(target.shape) != (self.D, self.D):
            raise ValueError("Target must be the complete physical Hpacked[D,D]")
        if not np.all(np.isfinite(self._numpy(target))):
            raise ValueError("Target contains nonfinite entries")
        # Only the symmetric target affects descent. Preserve the constant
        # antisymmetric contribution instead of silently changing the loss.
        self._target = .5 * (target + target.T)
        self._antisymmetric_loss = self._scalar(_sum((target - self._target) ** 2))
        self._E = self._fresh_residual()
        self.loss = self.initial_loss = self._loss(self._E)
        self.version = 0
        self.accepted = self.tested = 0
        self._W_sha = hashlib.sha256(self.W.astype("<f8").tobytes()).hexdigest()
        self._max_audit_residual_drift = 0.
        self._history = [dict(accepted=0,error2=math.sqrt(self.loss),loss=self.loss)]

    @property
    def words(self):
        result = self._words.view(); result.flags.writeable=False
        return result

    @property
    def U(self):
        result = self._U.view(); result.flags.writeable=False
        return result

    def _array(self, value):
        if self._torch is None:
            return np.array(value, dtype=np.float64, copy=True)
        if isinstance(value,np.ndarray) and not value.flags.writeable:
            value=np.array(value,copy=True)
        return self._torch.as_tensor(value, dtype=self._torch.float64, device=self.device).detach().clone()

    def _numpy(self, value):
        return np.asarray(value) if self._torch is None else value.detach().cpu().numpy()

    def _scalar(self, value):
        return float(value) if self._torch is None else float(value.item())

    def _decode(self, words):
        value = np.asarray(self.decoder(words), dtype=np.float64)
        if value.shape != tuple(words.shape[:-1]) + (self.N,):
            raise ValueError("Decoder returned the wrong vector shape")
        norm = np.linalg.norm(value, axis=-1, keepdims=True)
        if np.any(norm == 0) or not np.all(np.isfinite(value)):
            raise ValueError("Decoder produced nonfinite/zero vectors")
        return value / norm  # Matches official reconstruct_x.

    def _pack(self, u):
        return u[..., self.rows] * u[..., self.cols] * self.scale

    def _flat_X(self):
        return (self._X.transpose(1,0,2) if self._torch is None else self._X.permute(1,0,2)).reshape(self.D,-1)

    def _fresh_residual(self):
        x = self._flat_X()
        matrix=x@x.T
        return .5*(matrix+matrix.T)-self._target

    def _loss(self, residual):
        return self._scalar(_sum(residual * residual)) + self._antisymmetric_loss

    def word_gradient(self,*,return_geometry=False):
        """Exact continuous full-H gradient for deterministic proposal ranking."""
        EX = self._E @ self._flat_X()
        gradient = np.empty_like(self._words,dtype=np.float64)
        mass=np.empty_like(gradient) if return_geometry else None
        vnorm=np.empty((self.R,self.B)) if return_geometry else None
        for r in range(self.R):
            EY = self._numpy(EX[:,r*self.C:(r+1)*self.C] @ self._array(self.W[r].T))
            matrices = np.zeros((self.B,self.N,self.N),dtype=np.float64)
            packed = EY.T / self.scale
            matrices[:,self.rows,self.cols] = packed
            matrices[:,self.cols,self.rows] = packed
            gu = 8 * np.einsum("bij,bj->bi",matrices,self._U[r],optimize=True)
            if return_geometry:
                gradient[r],mass[r]=angle_vjp_numpy(self._words[r],self.edges,gu,
                    brot=self.brot,return_mass=True)
                wr=self._array(self.W[r])
                gram=self._X[r].T@self._X[r]
                vnorm[r]=self._numpy(_sum((wr@gram)*wr,1))
            else:
                gradient[r] = angle_vjp_numpy(self._words[r],self.edges,gu,brot=self.brot)
        return (gradient,mass,vnorm) if return_geometry else gradient

    def rank_candidates(self, top_k=64, *, gradient=None, gradient_callback=None,ranking='gradient'):
        if ranking not in {'gradient','gauss_newton'}:
            raise ValueError("ranking must be gradient or gauss_newton")
        if ranking=='gauss_newton':
            native_gradient,mass,vnorm=self.word_gradient(return_geometry=True)
        if gradient is None:
            gradient = (gradient_callback(self) if gradient_callback else
                        native_gradient if ranking=='gauss_newton' else self.word_gradient())
        gradient = np.asarray(gradient,dtype=np.float64)
        if gradient.shape != self._words.shape or not np.all(np.isfinite(gradient)):
            raise ValueError("Ranking gradient must be finite[R,B,K]")
        count=min(max(1,int(top_k)),gradient.size)
        if ranking=='gauss_newton':
            step=np.pi/(1<<(self.brot-1))
            overlap=1+(np.cos(step)-1)*mass
            # Exact norm of a unit-vector projector's one-angle delta; the
            # score omits smaller E-curvature/cross terms, ranking only.
            dnorm=np.maximum(0.,2*(1-overlap*overlap))
            score=-np.abs(gradient)*(np.sin(step)/step)+2*vnorm[:,:,None]*dnorm
        else:
            score=-np.abs(gradient)
        # Explicit flat-index tie breaking, independent of random sampling.
        indices=np.lexsort((np.arange(gradient.size),score.ravel()))[:count]
        result=[]
        for index in indices:
            r,b,k=np.unravel_index(index,self._words.shape)
            result.extend(((r,b,k,-1),(r,b,k,1)))
        return np.asarray(result,dtype=np.int64)

    def rank_pair_candidates(self,top_k=128,angles_per_vector=6):
        """Correlated two-word proposals; ranking approximate, deltas exact."""
        gradient,mass,vnorm=self.word_gradient(return_geometry=True)
        step=np.pi/(1<<(self.brot-1));overlap=1+(np.cos(step)-1)*mass
        single=-np.abs(gradient)*(np.sin(step)/step)+4*vnorm[:,:,None]*(1-overlap*overlap)
        K=min(int(angles_per_vector),self.K)
        selected=np.argsort(single,axis=-1,kind='stable')[...,:K].reshape(-1,K)
        aa,bb=np.triu_indices(K,1);pairs=len(aa);count=self.R*self.B
        rb=np.repeat(np.arange(count),pairs*4)
        k1=np.repeat(selected[:,aa],4,axis=1).ravel();k2=np.repeat(selected[:,bb],4,axis=1).ravel()
        d1=np.tile([-1,-1,1,1],count*pairs);d2=np.tile([-1,1,-1,1],count*pairs)
        flatwords=self._words.reshape(count,self.K);trial=flatwords[rb].copy()
        ids=np.arange(len(rb));trial[ids,k1]=(trial[ids,k1]+d1)%self.modulus;trial[ids,k2]=(trial[ids,k2]+d2)%self.modulus
        unew=self._decode(trial);old=self._U.reshape(count,self.N)[rb]
        ov=np.sum(unew*old,axis=1);dnorm=np.maximum(0.,2*(1-ov*ov))
        gg=gradient.reshape(count,self.K)
        score=(gg[rb,k1]*d1+gg[rb,k2]*d2)*(np.sin(step)/step)+2*vnorm.ravel()[rb]*dnorm
        order=np.lexsort((ids,score))[:min(top_k,len(ids))]
        return np.stack((rb[order]//self.B,rb[order]%self.B,k1[order],d1[order],k2[order],d2[order]),axis=1)

    def _candidate_components(self, coordinates):
        r,b=coordinates[:,:2].T
        k=coordinates[:,2::2];direction=coordinates[:,3::2]
        if coordinates.shape[1] not in (4,6) or np.any((direction != -1) & (direction != 1)):
            raise ValueError("Only exact +/-1 integer-word edits are allowed")
        if (np.any(r<0) or np.any(r>=self.R) or np.any(b<0) or np.any(b>=self.B)
                or np.any(k<0) or np.any(k>=self.K)):
            raise ValueError("Candidate coordinate outside the factor")
        proposed=self._words[r,b].copy()
        for edit in range(k.shape[1]):
            proposed[np.arange(len(coordinates)),k[:,edit]]=(proposed[np.arange(len(coordinates)),k[:,edit]]+direction[:,edit])%self.modulus
        u=self._decode(proposed)
        d=self._array((self._pack(u)-self._pack(self._U[r,b])).T)
        v=self._array(np.zeros((self.D,len(coordinates))))
        g=np.einsum("ij,ij->i",self.W[r,b],self.W[r,b])
        for rho in np.unique(r):
            ids=np.flatnonzero(r==rho)
            value=self._X[rho] @ self._array(self.W[r[ids],b[ids]].T)
            if self._torch is None:
                v[:,ids]=value
            else:
                v[:,self._torch.as_tensor(ids,device=self.device)]=value
        return proposed,u,d,v,self._array(g)

    def evaluate_candidates(self, coordinates, *, batch_size=100):
        coordinates=np.asarray(coordinates)
        if not np.issubdtype(coordinates.dtype,np.integer):
            raise ValueError("Candidate coordinates must be exact integers")
        coordinates=coordinates.astype(np.int64,copy=False)
        if coordinates.ndim!=2 or coordinates.shape[1] not in (4,6) or batch_size<1:
            raise ValueError("Expected[M,4]or[M,6]coordinates and positive batch_size")
        result=np.empty(len(coordinates),dtype=np.float64)
        for start in range(0,len(coordinates),batch_size):
            chunk=coordinates[start:start+batch_size]
            _,_,d,v,g=self._candidate_components(chunk)
            delta=exact_rank2_deltas(self._E,d,v,g,symmetric_residual=True)
            result[start:start+len(chunk)]=self._numpy(delta)
        if not np.all(np.isfinite(result)):
            raise ArithmeticError("Nonfinite exact candidate loss")
        self.tested+=len(result)
        return CandidateEvaluation(self.version,coordinates.copy(),result)

    def accept_best(self,evaluation,*,min_improvement=1e-14):
        if not math.isfinite(min_improvement) or min_improvement<0:
            raise ValueError("min_improvement must be finite and nonnegative")
        if evaluation.state_version!=self.version:
            raise ValueError("Stale candidate deltas; re-evaluate after every accepted edit")
        if not len(evaluation.delta_loss):
            return None
        index=int(np.argmin(evaluation.delta_loss))
        predicted=float(evaluation.delta_loss[index])
        if predicted>=-float(min_improvement):
            return None
        coordinates=evaluation.coordinates[index:index+1]
        proposed,u,d,v,g=self._candidate_components(coordinates)
        z=v[:,0]+.5*g[0]*d[:,0]
        change=d[:,0,None]*z[None,:]+z[:,None]*d[None,:,0]
        updated=self._E+change
        next_loss=self._loss(updated)
        measured_delta=next_loss-self.loss
        if abs(measured_delta-predicted)>5e-11*(1+self.loss):
            raise ArithmeticError("Rank-two prediction disagrees with explicit residual update")
        if measured_delta>=-float(min_improvement):
            return None  # Atomic: no words/U/X/E changed.
        r,b,k,direction=map(int,coordinates[0,:4])
        old_loss=self.loss
        self._X[r]+=d[:,0,None]*self._array(self.W[r,b][None,:])
        self._E=updated
        self._words[r,b]=proposed[0]
        self._U[r,b]=u[0]
        self.loss=next_loss
        self.version+=1
        self.accepted+=1
        row=dict(accepted=self.accepted,rho=r,b=b,angle=k,direction=direction,
                 predicted_delta=predicted,actual_residual_delta=measured_delta,
                 before_loss=old_loss,loss=self.loss,error2=math.sqrt(self.loss))
        if coordinates.shape[1]==6:row.update(second_angle=int(coordinates[0,4]),second_direction=int(coordinates[0,5]))
        self._history.append(row)
        return row

    def audit(self,*,atol=1e-9):
        # Reconstruct X from ALL current normalized rows and fixed W, not the
        # accumulated rank-two updates. Independent dense physical objective.
        decoded=self._decode(self._words)
        decoder_drift=float(np.max(np.abs(decoded-self._U)))
        if decoder_drift>1e-12:
            raise ArithmeticError("Cached U disagrees with current native integer words")
        fresh_X=self._array(np.einsum("rbd,rbc->rdc",self._pack(decoded),self.W,optimize=True))
        flat=(fresh_X.transpose(1,0,2) if self._torch is None else fresh_X.permute(1,0,2)).reshape(self.D,-1)
        matrix=flat@flat.T
        residual=.5*(matrix+matrix.T)-self._target
        drift=self._scalar(_sum((residual-self._E)**2))**.5
        fresh_loss=self._loss(residual)
        if drift>atol or abs(fresh_loss-self.loss)>atol:
            raise ArithmeticError("Accumulated state disagrees with full physical rebuild")
        if hashlib.sha256(self.W.astype('<f8').tobytes()).hexdigest()!=self._W_sha:
            raise ArithmeticError("Fixed W was modified")
        self._max_audit_residual_drift=max(self._max_audit_residual_drift,drift)
        return dict(error2=math.sqrt(fresh_loss),loss=fresh_loss,residual_drift=drift,
                    decoded_word_cache_drift=decoder_drift,W_unchanged=True)

    def export_words(self,*,include_one_body=True):
        body=(self._words%self.modulus).astype('<u2').reshape(-1,self.K)
        if include_one_body and self._one_body is not None:
            return np.concatenate((self._one_body,body))
        return body

    def polish(self,*,seconds=60.,max_steps=128,top_k=64,batch_size=100,
               gradient_callback=None,callback=None,audit_every=16,min_improvement=1e-14,
               ranking='gradient',proposals_per_gradient=1,pair_words=False):
        if not math.isfinite(seconds) or seconds<=0:
            raise ValueError("A positive finite time budget is required")
        started=time.monotonic()
        taken=0
        while taken<max(0,int(max_steps)):
            if time.monotonic()-started>=seconds:
                break
            proposals=(self.rank_pair_candidates(top_k) if pair_words else
                       self.rank_candidates(top_k,gradient_callback=gradient_callback,ranking=ranking))
            if time.monotonic()-started>=seconds:
                break
            accepted_in_pool=0
            for _ in range(max(1,int(proposals_per_gradient))):
                if not len(proposals) or taken>=max_steps or time.monotonic()-started>=seconds:
                    break
                # Ranking may be stale, but every delta and acceptance is
                # recomputed against the exact CURRENT integer model.
                evaluated=self.evaluate_candidates(proposals,batch_size=batch_size)
                chosen=evaluated.coordinates[int(np.argmin(evaluated.delta_loss))].copy()
                row=self.accept_best(evaluated,min_improvement=min_improvement)
                if row is None:break
                taken+=1;accepted_in_pool+=1
                proposals=proposals[~np.all(proposals[:,[0,1,2]]==chosen[None,[0,1,2]],axis=1)]
                if audit_every and self.accepted%audit_every==0:
                    row['full_rebuild_audit']=self.audit()
                if callback:callback(row,self.export_words(),self.W)
            if not accepted_in_pool:break
        audit=self.audit()
        return dict(status='EXACT_FULL_TARGET_TWO_BODY_DISCRETE_POLISH',backend=self.backend,ranking=ranking,
            brot=self.brot,accepted=self.accepted,tested=self.tested,
            initial_error2=math.sqrt(self.initial_loss),final_error2=audit['error2'],
            elapsed_seconds=time.monotonic()-started,W_unchanged=True,
            one_body_refreshed=False,H2_I_refitted=False,
            full_physical_acceptance_or_circuit_verification=False,
            antisymmetric_target_constant_loss=self._antisymmetric_loss,
            max_audit_residual_drift=self._max_audit_residual_drift,history=list(self._history),
            stop_scope='A pool with no descent is not a global integer optimum; time budget is checked between batches')

