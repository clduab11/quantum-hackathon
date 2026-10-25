import numpy as np
import pytest
from tasks.dfthcsos.factor_merge import merge_initialize, projectors


def fixture():
    rng = np.random.default_rng(95101)
    u = rng.normal(size=(4, 3, 5))
    w = rng.normal(size=(4, 3, 2)) * .1
    x = (projectors(u) @ w).transpose(1, 0, 2).reshape(15, -1)
    return dict(U=u, W=w, H2_I=np.zeros((4, 2))), x @ x.T


def test_merge_preserves_all_groups_without_rank_truncation():
    params, target = fixture()
    out, report = merge_initialize(params, target, (2, 6, 4), 2)
    x = (projectors(out['U']) @ out['W']).transpose(1, 0, 2).reshape(15, -1)
    np.testing.assert_allclose(x @ x.T, target, atol=1e-12)
    assert sorted(sum(report['groups'], [])) == list(range(4))


def test_merge_sweeps_reduce_residual_and_repeat():
    params, target = fixture()
    a, report = merge_initialize(params, target, (2, 4, 3), 3)
    b, _ = merge_initialize(params, target, (2, 4, 3), 3)
    np.testing.assert_array_equal(a['W'], b['W'])
    errors = [report['initial_error'], *[r['error'] for r in report['sweeps']]]
    assert all(y <= x + 1e-12 for x, y in zip(errors, errors[1:]))


def test_merge_rejects_unavailable_rank():
    params, target = fixture()
    with pytest.raises(ValueError, match='dimensions'):
        merge_initialize(params, target, (2, 16, 3), 1)


def test_gauss_newton_derivatives_against_independent_dense_forms():
    from tasks.dfthcsos.factor_gauss_newton import Geometry
    params, _ = fixture()
    g = Geometry(params['U'], params['W'])
    rng = np.random.default_rng(78)
    step = rng.normal(size=g.u.size + g.w.size)
    z = rng.normal(size=g.x.shape)
    dx = g.jvp(step)
    assert np.sum(dx*z) == pytest.approx(step @ g.vjp(z), abs=1e-10)
    up, wp = g.trial(step, 1e-6)
    um, wm = g.trial(step, -1e-6)
    finite = (g.columns(projectors(up) @ wp)-g.columns(projectors(um) @ wm))/2e-6
    np.testing.assert_allclose(dx, finite, atol=1e-9)
    dr = dx @ g.x.T + g.x @ dx.T
    assert step @ g.normal(step) == pytest.approx(np.sum(dr**2), abs=1e-9)


def test_gauss_newton_reduces_full_residual():
    from tasks.dfthcsos.factor_gauss_newton import refine
    params, target = fixture()
    params['W'] *= 1.1
    initial = np.linalg.norm((1.1**2-1)*target)
    out, report = refine(params, target, 3, 10)
    errors = [r['error'] for r in report['history']]
    assert errors[-1] < initial
    assert all(y <= x for x, y in zip(errors, errors[1:]))


def test_floor_requires_both_errors_and_strict_physical_floors():
    from tasks.dfthcsos.factor_measure import floor_problems
    good = dict(error_1=.0195, error_2=.0195, Lambda=49.001,
                E_gap=3.915048, lambda_eff=19., gap_in_domain=True)
    assert floor_problems(good, 3.) == []
    for name, bad in [('error_1', .0196), ('error_2', .0196),
                      ('Lambda', 49.), ('E_gap', 3.914898),
                      ('lambda_eff', float('nan')), ('error_1', float('nan'))]:
        assert floor_problems(good | {name:bad}, 3.)
    assert floor_problems(good, 2.99)
