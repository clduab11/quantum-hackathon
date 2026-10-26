"""Independent numerical checks for the CUDA port and exact discrete helpers."""
import os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
import numpy as np
import pytest
from tasks.dfthcsos.gpu_fit.fixed import qr_model
from tasks.dfthcsos.gpu_fit.gauge import deterministic_column_gauge
from tasks.dfthcsos.gpu_fit.geometry import columns
from tasks.dfthcsos.gpu_fit.integer import ExactAnglePolisher, decode_numpy, exact_rank2_deltas


def factors():
    rng = np.random.default_rng(95101)
    u, w = rng.normal(size=(2,4,6)), rng.normal(size=(2,4,3))*.1
    u /= np.linalg.norm(u, axis=-1, keepdims=True)
    return rng, u, w


def test_qr_loss_and_gradient_match_dense_frobenius():
    rng, u, w = factors()
    h = columns(u, w) @ columns(u, w).T + np.eye(21)*.001
    v, quantities, to_w, _ = qr_model(u, w, h)
    trial = v + rng.normal(size=v.shape)*.002
    x = columns(u, to_w(trial))
    loss, grad = quantities(trial)
    assert loss == pytest.approx(np.sum((x@x.T-h)**2), abs=1e-12)
    direction = rng.normal(size=v.shape)
    eps = 1e-6
    finite = (quantities(trial+eps*direction)[0]-quantities(trial-eps*direction)[0])/(2*eps)
    assert finite == pytest.approx(np.sum(grad*direction), rel=1e-6, abs=1e-10)


def test_column_gauge_preserves_augmented_gram_and_improves_norm():
    rng, u, w = factors()
    p = dict(U=u, W=w, H2_I=rng.normal(size=(2,3))*.1)
    augmented = np.concatenate([w,p['H2_I'][:,None]],axis=1)
    result, report = deterministic_column_gauge(p,plane_sweeps=1)
    changed = np.concatenate([result['W'],result['H2_I'][:,None]],axis=1)
    np.testing.assert_allclose(changed@changed.swapaxes(1,2),augmented@augmented.swapaxes(1,2),atol=1e-10)
    assert report['new_l1_square'] <= report['old_l1_square']+1e-12


def test_exact_integer_delta_matches_dense_update_and_rejects_stale_state():
    rng=np.random.default_rng(78)
    e=rng.normal(size=(10,10));e=(e+e.T)/2
    d,v=rng.normal(size=(10,2)),rng.normal(size=(10,2));g=np.array([.3,.7])
    actual=exact_rank2_deltas(e,d,v,g)
    for k in range(2):
        update=np.outer(v[:,k],d[:,k])+np.outer(d[:,k],v[:,k])+g[k]*np.outer(d[:,k],d[:,k])
        assert actual[k]==pytest.approx(np.sum((e+update)**2)-np.sum(e**2),abs=1e-10)
    edges=np.array([[0,1],[0,2],[1,3]])
    words=np.array([[8,12,3],[24,7,13]])
    w=rng.normal(size=(1,2,2))*.1
    target_words=words.copy();target_words[0,0]+=1
    x=columns(decode_numpy(target_words,edges,brot=8)[None],w)
    p=ExactAnglePolisher(words,w,edges,x@x.T,brot=8)
    proposal=p.evaluate_candidates(np.array([[0,0,0,1]]))
    assert p.accept_best(proposal) is not None
    assert p.audit()['error2'] < 1e-10
    with pytest.raises(ValueError,match='Stale'):
        p.accept_best(proposal)
    with pytest.raises(ValueError,match='float64'):
        exact_rank2_deltas(e.astype(np.float32),d,v,g)


def cuda():
    torch=pytest.importorskip('torch')
    if not torch.cuda.is_available():pytest.skip('CUDA hardware unavailable')
    torch.set_num_threads(2)
    return torch


def test_gpu_tangent_jvp_vjp_and_normal_against_dense_form():
    torch=cuda()
    from tasks.dfthcsos.gpu_fit.gauss_newton import Geometry
    rng,u,w=factors();g=Geometry(u,w,dtype='float64')
    vector=torch.tensor(rng.normal(size=g.nu+g.w.numel()),device='cuda',dtype=torch.float64)
    z=torch.tensor(rng.normal(size=g.x.shape),device='cuda',dtype=torch.float64)
    assert float((g.jvp(vector)*z).sum())==pytest.approx(float(vector@g.vjp(z)),abs=1e-10)
    dx=g.jvp(vector);dr=dx@g.x.T+g.x@dx.T
    assert float(vector@g.normal(vector))==pytest.approx(float((dr*dr).sum()),abs=1e-9)
    ep=1e-6;up,wp=g.apply(vector,ep);um,wm=g.apply(vector,-ep)
    finite=(g.trial_x(up,wp)-g.trial_x(um,wm))/(2*ep)
    torch.testing.assert_close(finite,dx,rtol=1e-7,atol=1e-9)


def test_cuda_continuous_stages_reduce_a_synthetic_residual():
    cuda()
    from tasks.dfthcsos.gpu_fit.continuous import structural, gauss_newton
    from tasks.dfthcsos.gpu_fit.geometry import physical_error
    _,u,w=factors();x=columns(u,w);target=x@x.T
    initial=w*.6;seen=[]
    callback=lambda u,w,details:seen.append(details)
    un,wn,lbfgs=structural(u,initial,target,callback,steps=2,seconds=60)
    assert lbfgs['calls']>0 and seen
    assert physical_error(un,wn,target)<physical_error(u,initial,target)
    un,wn,gn=gauss_newton(u,initial,target,callback,iterations=2,cg_iterations=5,seconds=60)
    assert gn['cg_iterations']>0
    assert physical_error(un,wn,target)<physical_error(u,initial,target)


@pytest.mark.parametrize('compiled', [False, True])
def test_gpu_progressive_freeze_emits_valid_words_and_checkpoints(monkeypatch, compiled):
    torch=cuda()
    from types import SimpleNamespace
    from tasks.dfthcsos.gpu_fit.quantize import quantize,EDGES,Tree
    # Small synthetic math test; eager and compiled paths use the same objective.
    if not compiled:
        monkeypatch.setattr(torch,'compile',lambda f:f)
    rng=np.random.default_rng(95101)
    u=rng.normal(size=(1,2,76));u/=np.linalg.norm(u,axis=-1,keepdims=True)
    w=rng.normal(size=(1,2,2))*.01
    x=columns(u,w);i,j=np.tril_indices(76)
    tg=SimpleNamespace(Ts=torch.tensor(x@x.T,dtype=torch.float32,device='cuda'),
        ri=torch.tensor(i,device='cuda'),ci=torch.tensor(j,device='cuda'),
        scale=torch.tensor(np.where(i==j,1.,np.sqrt(2.)),dtype=torch.float32,device='cuda'))
    ut=torch.tensor(u,dtype=torch.float32,device='cuda');wt=torch.tensor(w,dtype=torch.float32,device='cuda')
    seen=[]
    words,weights=quantize(ut,wt,tg,brot=8,steps=2,final_steps=2,probes=1,fracs=(.5,1.),
                          log=lambda _:None,callback=lambda u,w,s:seen.append(s))
    assert seen==[0,1,2] and np.isfinite(weights).all()
    assert words.shape==(2,75) and words.min()>=0 and words.max()<256
    angles=torch.tensor(words/128,dtype=torch.float32,device='cuda')
    np.testing.assert_allclose(Tree()(angles).cpu().numpy(),decode_numpy(words,EDGES,brot=8),atol=2e-6)
    with pytest.raises(ValueError,match='CPU fitting'):
        quantize(ut.cpu(),wt.cpu(),tg)
