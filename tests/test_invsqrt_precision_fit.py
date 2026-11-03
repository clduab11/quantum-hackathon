"""A precision experiment must fit the requested quantizer, not the default one."""
import numpy as np
import pytest

from tasks.invsqrt.public_port import fit
from tasks.invsqrt.public_port.model import Config


@pytest.mark.parametrize('guard,bias', [(0, 0), (1, .5), (2, 1.5)])
def test_anchor_center_accounts_for_truncation_guard(guard, bias):
    values = np.array([[10., 14., 12.], [20., 21., 24.]])
    center = getattr(fit, 'anchor_center', None)
    assert center is not None, 'the fitter must expose its quantizer-dependent anchor center'
    np.testing.assert_array_equal(center(values, Config(gy=guard)), [12+bias, 22+bias])


def test_nondefault_fit_propagates_config_and_records_parameters(monkeypatch):
    requested = Config(f1=17, fyr=25, gy=1)
    calls = []

    def group(e, group, group_bits, fraction_bits, cfg=None):
        calls.append(cfg)
        return dict(score=.5, base=100, step=0, rows=[(100, 1000, 10000)]*(1 << group_bits))

    monkeypatch.setattr(fit, 'fit_group', group)
    monkeypatch.setattr(fit, 'certificate', lambda cfg, tables: {'passed': cfg == requested})
    import inspect
    assert 'cfg' in inspect.signature(fit.fit_tables).parameters, 'fit_tables must accept a precision configuration'
    result = fit.fit_tables(cfg=requested)
    assert calls and all(cfg == requested for cfg in calls)
    assert result['params'] == [9, 17, 25, 1, [5]]
    assert result['certificate']['passed']


def test_original_quantizer_center_is_unchanged():
    center = getattr(fit, 'anchor_center', None)
    assert center is not None
    values = np.array([[.25, 9.75]])
    np.testing.assert_array_equal(center(values, Config()), [6.5])


def test_default_generator_rejects_experimental_precision_before_build():
    from tasks.invsqrt.public_port.generate import build_from_fit

    with pytest.raises(ValueError, match='precision'):
        build_from_fit({'params': [9, 17, 25, 1, [5]], 'rows': []})
