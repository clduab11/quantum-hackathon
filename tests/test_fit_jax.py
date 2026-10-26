"""GPU loss checks; optional JAX dependency, no CPU fitting fallback."""
import numpy as np
import pytest

jax = pytest.importorskip('jax')
import jax.numpy as jnp
from tasks.dfthcsos.fit_jax.angles import quantize, decode
from tasks.dfthcsos.fit_jax.assignment import assign
from tasks.dfthcsos.fit_jax.loss import terms, objective

jax.config.update('jax_enable_x64', True)


@pytest.fixture(autouse=True)
def accelerator():
    devices = [d for d in jax.devices() if d.platform in ('gpu', 'tpu')]
    if not devices:
        pytest.skip('JAX GPU/TPU required; CPU fitting is forbidden')
    with jax.default_device(devices[0]):
        yield


@pytest.mark.parametrize('bits', [12, 11, 8])
def test_rounding_half_up_modulo_and_surrogate(bits):
    scale = 2**(bits-1)
    angles = jnp.array([-2., -0.5/scale, 0.5/scale, 2.-0.5/scale, 2.+0.5/scale])
    expected = np.floor(np.mod(np.asarray(angles), 2)*scale+.5) % (2**bits) / scale
    np.testing.assert_array_equal(quantize(angles, bits), expected)
    np.testing.assert_array_equal(jax.grad(lambda a: quantize(a, bits).sum())(angles), 1.)


def test_decode_non_path_tree_and_normalization():
    from math import pi
    angles = np.array([[.1,.3,-.2], [1.,0.,.5]])
    edges = np.array([[0,2],[0,1],[2,3]])
    expected = np.zeros((2,4)); expected[:,0] = 1
    for k,(p,c) in enumerate(edges):
        a,b = expected[:,p].copy(),expected[:,c].copy()
        co,si = np.cos(pi*angles[:,k]),np.sin(pi*angles[:,k])
        expected[:,p],expected[:,c] = co*a-si*b,si*a+co*b
    np.testing.assert_allclose(decode(jnp.array(angles),jnp.array(edges)),expected,atol=1e-14,rtol=0)


def test_assignment_matches_scipy_and_beats_greedy():
    from scipy.optimize import linear_sum_assignment
    rng = np.random.default_rng(251)
    matrices = [np.array([[.9,.8],[.85,.1]])] + [rng.normal(size=(n,n)) for n in (3,8,76)]
    for overlap in matrices:
        result = np.asarray(jax.jit(assign)(jnp.array(overlap)))
        rows, cols = linear_sum_assignment(-overlap)
        assert len(np.unique(result)) == len(result)
        np.testing.assert_allclose(overlap[rows,result].sum(),overlap[rows,cols].sum(),atol=1e-12,rtol=0)


def test_floor_penalties_are_strict_and_directional():
    valid = dict(error_1=jnp.array(.01),error_2=jnp.array(.01),Lambda=jnp.array(60.),E_gap=jnp.array(4.))
    for name,value in [('Lambda',49.),('E_gap',3.914898),('error_1',.021),('error_2',.021)]:
        bad = {**valid,name:jnp.array(value)}
        # Violating a floor must increase penalty, independently of score changes.
        assert float(objective(bad, score_weight=0)) > float(objective(valid, score_weight=0))
    assert float(jax.grad(lambda x: objective({**valid,'Lambda':x},score_weight=0))(48.)) < 0
    assert float(jax.grad(lambda x: objective({**valid,'E_gap':x},score_weight=0))(3.)) < 0


def test_declared_public_factor_mirror():
    import os
    from pathlib import Path
    from tasks.dfthcsos.fit_jax.mirror import mirror
    names = ('VQCC_STARTER','VQCC_COMPETITION','VQCC_PUBLIC_FACTOR')
    if not all(os.environ.get(k) for k in names):
        pytest.skip('set VQCC_STARTER, VQCC_COMPETITION and VQCC_PUBLIC_FACTOR for pinned integration test')
    report = mirror(*(Path(os.environ[k]) for k in names))
    assert report['max_absolute_difference'] <= 1e-10
    assert [p['bits'] for p in report['points']] == [12,11,8]


def test_mirror_rejects_absolute_error_and_nan():
    from tasks.dfthcsos.fit_jax.mirror import compare
    with pytest.raises(AssertionError,match='E_SOS mirror differs'):
        compare({'E_SOS':-22144.+1e-8},{'E_SOS':-22144.})
    with pytest.raises(AssertionError,match='error_1 mirror differs'):
        compare({'error_1':float('nan')},{'error_1':0.})


def test_weight_offset_derivatives_against_finite_differences():
    from scipy.optimize._numdiff import approx_derivative
    rng = np.random.default_rng(251)
    n,r,b,c = 4,1,3,2
    params = dict(angles=jnp.array(rng.uniform(0,2,(n+r*b,n-1))),
                  w=jnp.array(rng.normal(size=(r,b,c))),offsets=jnp.array(rng.normal(size=(r,c))))
    fixed = dict(target=jnp.eye(10),h1_thc=jnp.diag(jnp.arange(n,dtype=float)+20),
                 S=jnp.eye(n),beta_1=jnp.array(.1),electrons=jnp.array(2),
                 ecore=jnp.array(0.),energy_upper=jnp.array(4.))
    edges = jnp.array([[0,1],[0,2],[2,3]])
    for key in ('w','offsets'):
        shape = params[key].shape
        def fun(x):
            m = terms({**params,key:x.reshape(shape)},fixed,edges,11)
            return m['error_1']+m['error_2']+.1*m['Lambda']+.1*m['E_SOS']
        compiled = jax.jit(fun)
        flat = params[key].ravel()
        numeric = approx_derivative(lambda x:float(compiled(jnp.array(x))),np.asarray(flat)).ravel()
        np.testing.assert_allclose(jax.jit(jax.grad(fun))(flat),numeric,atol=2e-7,rtol=2e-5)
