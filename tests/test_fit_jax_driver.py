"""Driver safety checks plus an opt-in, real 15-minute official-cascade smoke."""
import os
from pathlib import Path
import numpy as np
import pytest
jax = pytest.importorskip('jax')
import jax.numpy as jnp
from tasks.dfthcsos.fit_jax.optimizer import step
from tasks.dfthcsos.fit_jax.export import arrays
from tasks.dfthcsos.fit_jax.loss import objective
jax.config.update('jax_enable_x64',True)


@pytest.fixture(autouse=True)
def gpu():
    devices = [d for d in jax.devices() if d.platform in ('gpu','tpu')]
    if not devices:
        pytest.skip('GPU/TPU required; CPU fitting is forbidden')
    with jax.default_device(devices[0]):
        yield


def metrics(lam=60.):
    return dict(error_1=jnp.array(.01),error_2=jnp.array(.01),Lambda=jnp.array(lam),
                E_gap=jnp.array(4.),E_SOS=jnp.array(-10.))


def test_rejected_proposals_roll_back_parameters_and_moments():
    params = dict(x=jnp.array([1.]))
    moments = (dict(x=jnp.zeros(1)),dict(x=jnp.zeros(1)))
    seen = []
    def invalid(proposal):
        seen.append(float(proposal['x'][0]))
        return metrics(49.)
    result,state,actual,trials = step(params,moments,1,dict(x=jnp.ones(1)),invalid,.001,100.,attempts=3)
    assert result is params and state is moments and actual is None
    assert len(seen) == len(trials) == 3
    assert not any(t['admissible'] for t in trials)


def test_backtracking_accepts_only_feasible_improvement():
    params = dict(x=jnp.array([60.]))
    zeros = dict(x=jnp.zeros(1))
    def evaluate(p):
        return metrics(p['x'][0])
    result,state,actual,trials = step(params,(zeros,zeros),1,dict(x=jnp.ones(1)),evaluate,16.,float(objective(metrics())))
    assert len(trials) == 2 and not trials[0]['admissible'] and trials[1]['admissible']
    assert float(result['x'][0]) == pytest.approx(52.)
    assert actual is not None and float(state[0]['x'][0]) > 0


def test_export_keeps_free_one_body_words_and_native_offsets(tmp_path):
    from tasks.dfthcsos.factor_support import write_npz
    p = dict(angles=jnp.array([[.1,.2],[.3,.4],[.5,.6],[.7,.8]]),
             w=jnp.array([[[2.]]]),offsets=jnp.array([[3.]]))
    edges = jnp.array([[0,1],[1,2]])
    template = dict(H1_I=1.,Hsym_lower=np.zeros(6))
    output = arrays(p,edges,11,template)
    expected = np.floor(np.asarray(p['angles'])*1024+.5).astype(int)
    np.testing.assert_array_equal(output['angle_words'],expected)
    assert output['H2_I'][0,0] == 5.
    changed = arrays({**p,'angles':p['angles'].at[0,0].add(.1)},edges,11,template)
    assert changed['angle_words'][0,0] != output['angle_words'][0,0]
    np.testing.assert_array_equal(changed['U'],output['U'])
    path = tmp_path/'factor.npz'
    write_npz(path,output)
    with pytest.raises(FileExistsError):
        write_npz(path,changed)
    with np.load(path) as saved:
        np.testing.assert_array_equal(saved['angle_words'],expected)


def test_official_gpu_smoke(tmp_path):
    if os.environ.get('VQCC_RUN_JAX_SMOKE') != '1':
        pytest.skip('opt in with VQCC_RUN_JAX_SMOKE=1; runs GPU fit and full circuit cascade')
    from argparse import Namespace
    from tasks.dfthcsos.fit_jax.run import run
    names = ('VQCC_STARTER','VQCC_COMPETITION','VQCC_PUBLIC_FACTOR')
    if not all(os.environ.get(k) for k in names):
        pytest.fail('smoke opt-in needs all three VQCC input paths')
    paths = [Path(os.environ[k]) for k in names]
    report = run(Namespace(starter=paths[0],competition=paths[1],factor=paths[2],
                         out=tmp_path/'smoke',bits=11,fit_seconds=300,steps=32,rate=1e-4,dry_run=False))
    assert report['training']['accepted_steps'] > 0
    assert report['cascade']['metrics']['stage3_passed'] == 1
    assert report['cascade']['metrics']['ratio'] >= 4
    assert report['seconds'] <= 900
    assert report['smoke_pass']


def test_gpu_reduction_preserves_rows_and_cannot_grow():
    from tasks.dfthcsos.fit_jax.reduce import reduce
    p = dict(angles=jnp.arange(12,dtype=float).reshape(6,2)/20,
             w=jnp.array([[[1.,0.],[0.,2.],[0.,0.]]]),offsets=jnp.array([[0.,0.]]))
    q = reduce(p,(1,2,1))
    assert q['w'].shape == (1,2,1) and q['angles'].shape == (5,2)
    np.testing.assert_array_equal(q['angles'][:3],p['angles'][:3])
    np.testing.assert_array_equal(q['angles'][3:],p['angles'][3:5])
    assert float(jnp.linalg.norm(q['w'])) == pytest.approx(2.)
    assert all(a.device.platform in ('gpu','tpu') for a in jax.tree.leaves(q))
    with pytest.raises(ValueError,match='cannot grow'):
        reduce(p,(1,4,2))
