"""Audit accounting against the supplied verifier helpers and published constants."""
import math

import pytest

from harness.costs import dfthcsos_cost, dqi_cost, effective_lambda, invsqrt_cost
from harness.runtime import load_metric

load_metric()
from dqi.verify_submission_dqi import clopper_pearson_upper_bound, repetition_overhead
from invsqrt.verify_submission_invsqrt import rotation_t_count


@pytest.mark.parametrize('failures,epsilon,repetition', [
    (0, 0.0008660587301657926, 1.1912604648115832),
    (1, 0.0009104197583220583, 1.1967314991687559),
])
def test_confidence_and_repetition(failures, epsilon, repetition):
    upper = clopper_pearson_upper_bound(failures, 102400, log2_delta=-128)
    assert upper == pytest.approx(epsilon, rel=1e-12)
    assert repetition_overhead(upper) == pytest.approx(repetition, rel=1e-12)
    assert repetition_overhead(upper) == math.log(2) / -math.log(.5 + 2 * math.sqrt(upper))


def test_zero_failure_bound_without_loss_of_precision():
    assert clopper_pearson_upper_bound(0, 102400) == -math.expm1(-128 * math.log(2) / 102400)


@pytest.mark.parametrize('epsilon', [-1, 1/16, float('nan')])
def test_invalid_repetition(epsilon):
    with pytest.raises(ValueError):
        repetition_overhead(epsilon)


def test_reference_lambda_and_cost():
    # Supplied SCORING_README.md, baseline rounded-angle metrics.
    value = effective_lambda(308.4559397330944, 3.965477244291833)
    assert value == pytest.approx(49.30136925057438)
    assert dfthcsos_cost(730, 93237, value) == pytest.approx(3355599588.3155365)


def test_public_lineage_cost_regression():
    # Public v3 source hardcodes this lambda_eff; it does not provide Lambda/E_gap.
    # This checks the reported scalar and cost, not that factorization's derivation.
    value = 47.558542335159316
    assert round(value, 2) == 47.56
    cost = dfthcsos_cost(681, 71958, value)
    assert 3355599588.3155365 / cost == pytest.approx(1.44, abs=.001)


@pytest.mark.parametrize('normalization,gap', [(308, 0), (308, 616), (308, -1), (math.inf, 4), (308, math.nan)])
def test_lambda_domain(normalization, gap):
    with pytest.raises(ValueError):
        effective_lambda(normalization, gap)


def test_invsqrt_includes_synthesized_rotations():
    total_t = 1 + 37 * rotation_t_count(2**-40)
    assert invsqrt_cost(260, 7735, total_t) == pytest.approx(260 * (7735 + (1 + 37 * 27.7) / 4))


def test_dqi_squares_space_and_uses_toffolis():
    cost = dqi_cost(1893, 5725461, repetition_overhead(clopper_pearson_upper_bound(0, 102400)))
    assert cost == pytest.approx(2.444153201267753e13, rel=.001)
