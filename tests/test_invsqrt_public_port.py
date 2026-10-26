# SPDX-License-Identifier: Apache-2.0
"""Public-source port arithmetic, independent of kickmix and GPU availability."""
import numpy as np
import pytest

from tasks.invsqrt.public_port.model import Config, pipeline, interpolation_values


def rounded(value, shift):
    if shift < 0:
        return value * 2 ** -shift
    return (value + (2 ** (shift - 1) if shift else 0)) // 2**shift


def test_pipeline_matches_scalar_signed_digit_definition():
    cfg = Config()
    ds = np.array([0, 1, 2, 31, 1024, 8191, 16383], dtype=np.int64)
    r, q = pipeline(cfg, 137, 180001, ds)
    for i, d in enumerate(ds):
        signs = [1 if int(d) & (1 << bit) else -1 for bit in range(14)]
        expected_r = 180001 - sum(signs[j] * rounded(137, cfg.sh2[j]) for j in cfg.rrow_list())
        expected_q = sum(signs[j] * rounded(expected_r, cfg.sh1[j]) for j in range(14))
        assert (int(r[i]), int(q[i])) == (expected_r, expected_q)


def test_interpolation_uses_address_bits_and_signed_rounding():
    assert interpolation_values(100, 3, fraction_bits=2, group_bits=2) == (103, 101, 99, 97)
    with pytest.raises(ValueError, match="curvature"):
        interpolation_values(0, 3, fraction_bits=2, group_bits=2)


def test_certificate_checks_every_input_and_catches_wrong_phase(monkeypatch):
    from tasks.invsqrt.public_port import model

    monkeypatch.setattr(model, 'MAX_X', 2)
    tables = {(e, a): (0, 0, 0) for e in range(2) for a in range(128)}
    report = model.certificate(Config(), tables)
    assert report['tested_inputs'] == 2
    assert report['passed'] is False
    assert report['first_bad_x'] == 2
    assert report['min_margin_units'] < 0


def test_gpu_arithmetic_matches_numpy():
    torch = pytest.importorskip('torch')
    if not torch.cuda.is_available():
        pytest.skip('CUDA unavailable')
    cfg = Config()
    ds = np.arange(16384, dtype=np.int64)
    expected = pipeline(cfg, 137, 180001, ds)
    actual = pipeline(cfg, 137, 180001, torch.tensor(ds, device='cuda'))
    for cpu, gpu in zip(expected, actual):
        np.testing.assert_array_equal(cpu, gpu.cpu().numpy())


def test_build_recomputes_mirror_instead_of_trusting_saved_pass(monkeypatch):
    from tasks.invsqrt.public_port import generate, model

    monkeypatch.setattr(model, 'MAX_X', 2)
    fitted = dict(rows=[(0, 0, 0)]*256, certificate={'passed': True})
    with pytest.raises(ValueError, match='G2 integer mirror failed before circuit'):
        generate.build_from_fit(fitted)
