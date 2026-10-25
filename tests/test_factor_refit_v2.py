import numpy as np
import pytest
from scipy.optimize._numdiff import approx_derivative

from tasks.dfthcsos.factor_reseed import regroup
from tasks.dfthcsos.factor_quantized import weight_value_grad, refit_quantized


def factors():
    rng = np.random.default_rng(235)
    return dict(U=rng.normal(size=(4, 3, 4)), W=rng.normal(size=(4, 3, 2)),
                H2_I=rng.normal(size=(4, 2)), H1_I=np.array(1.),
                Hsym_lower=np.zeros(10))


def tensor(p):
    u = p['U'] / np.linalg.norm(p['U'], axis=-1, keepdims=True)
    x = np.einsum('rbp,rbq,rbc->rcpq', u, u, p['W'])
    return np.einsum('rcpq,rckl->pqkl', x, x)


def test_regroup_exact_merge_preserves_tensor_and_one_body_absorption():
    p = factors()
    q = regroup(p, 2, 6, 4)
    np.testing.assert_allclose(tensor(q), tensor(p), atol=1e-12)
    assert q['W'].shape == (2, 6, 4)
    def absorption(p):
        u = p['U'] / np.linalg.norm(p['U'], axis=-1, keepdims=True)
        x = np.einsum('rbp,rbq,rbc->rcpq', u, u, p['W'])
        return np.einsum('rc,rcpq->pq', p['H2_I'] - p['W'].sum(axis=1), x)
    np.testing.assert_allclose(absorption(q), absorption(p), atol=1e-12)
    np.testing.assert_array_equal(q['Hsym_lower'], p['Hsym_lower'])


def test_regroup_compression_growth_and_determinism():
    p = factors()
    a, b = regroup(p, 1, 5, 4), regroup(p, 1, 5, 4)
    assert a['U'].shape == (1, 5, 4)
    assert a['W'].shape == (1, 5, 4)
    for k in a:
        np.testing.assert_array_equal(a[k], b[k])
    assert np.isfinite(tensor(a)).all()
    with pytest.raises(ValueError, match='available'):
        regroup(p, 2, 7, 3)
    with pytest.raises(ValueError, match='positive'):
        regroup(p, 0, 3, 3)


def test_quantized_weight_gradient_and_fit():
    rng = np.random.default_rng(6)
    v = rng.normal(size=(2, 3, 6))
    w = rng.normal(size=(2, 3, 2))
    target = rng.normal(size=(6, 6))
    target = (target + target.T) / 2
    fun = lambda x: weight_value_grad(x, w.shape, v, target, .003)
    np.testing.assert_allclose(fun(w.ravel())[1],
        approx_derivative(lambda x: fun(x)[0], w.ravel()).ravel(), rtol=2e-5, atol=2e-6)
    p = factors()
    # Deterministic grid fixture: tests the fixed rounded-vector contract.
    def rounded(u):
        v = np.round(u * 2) / 2
        return v / np.linalg.norm(v, axis=-1, keepdims=True)
    q, info = refit_quantized(p, np.eye(10), 8, 0., rounded, maxcor=7)
    np.testing.assert_array_equal(q['U'], rounded(p['U']))
    assert info['objective'] <= info['initial_objective']
    assert info['maxcor'] == 7
    assert info['iterations'] > 0
    with pytest.raises(ValueError, match='positive'):
        refit_quantized(p, np.eye(10), 0, 0., rounded)
