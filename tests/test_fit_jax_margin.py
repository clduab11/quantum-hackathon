"""Phase M must allow infeasible training, but never call it exportable."""
import numpy as np
import pytest
jax = pytest.importorskip('jax')
import jax.numpy as jnp
from tasks.dfthcsos.fit_jax.margin_loss import penalty, eligible, effective
from tasks.dfthcsos.fit_jax.margin_optimizer import fit
from tasks.dfthcsos.fit_jax.word_jumps import samples, summarize
jax.config.update('jax_enable_x64',True)


def test_fixed_paired_sampling_and_absolute_percentile():
    points = samples((572,75))
    assert points == samples((572,75)) and len(points) == 1000
    assert len({(r,c) for r,c,_ in points}) == 500
    for a,b in zip(points[::2],points[1::2]):
        assert a[:2] == b[:2] and (a[2],b[2]) == (-1,1)
    records = [dict(delta={k:v for k in ('error_2','E_gap','lambda_eff')}) for v in (-100.,0.,1.)]
    assert summarize(records)['E_gap']['absolute_p95'] == pytest.approx(90.1)


def test_training_crosses_infeasible_states_but_export_guard_rejects():
    devices = [d for d in jax.devices() if d.platform in ('gpu','tpu')]
    if not devices:
        pytest.skip('GPU/TPU required')
    with jax.default_device(devices[0]):
        def evaluate(p):
            return dict(error_1=jnp.array(.01),error_2=.03+p['w'][0],Lambda=jnp.array(100.),
                        E_gap=jnp.array(4.),E_SOS=jnp.array(-100.))
        p = {k:jnp.zeros(1) for k in ('angles','w','offsets')}
        target = dict(m2=.0005,mg=.001,cap=1.01*float(effective(evaluate(p))))
        records = []
        selected,best,report = fit(p,evaluate,target,30,2,lambda q,r:records.append(r))
        assert selected is None and report['steps'] == 2
        assert float(best['w'][0]) < 0
        assert not bool(eligible(evaluate(best),target))
        assert float(penalty(evaluate(best),target)) < float(penalty(evaluate(p),target))
        good = {**evaluate(p),'error_2':jnp.array(.0194)}
        assert bool(eligible(good,target))
        for changed in ({'E_gap':3.914898},{'Lambda':49.},{'error_1':.021},{'error_2':float('nan')}):
            assert not bool(eligible({**good,**changed},target))


def test_nonfinite_gradient_fails_loudly():
    devices = [d for d in jax.devices() if d.platform in ('gpu','tpu')]
    if not devices:
        pytest.skip('GPU/TPU required')
    with jax.default_device(devices[0]):
        p = {k:jnp.zeros(1) for k in ('angles','w','offsets')}
        def evaluate(q):
            return dict(error_1=jnp.array(.01),error_2=q['w'][0]*jnp.nan,
                        Lambda=jnp.array(100.),E_gap=jnp.array(4.),E_SOS=jnp.array(-100.))
        with pytest.raises(ValueError,match='nonfinite Phase M gradient'):
            fit(p,evaluate,dict(m2=.0005,mg=.001,cap=30.),30,2,lambda *a:None)
