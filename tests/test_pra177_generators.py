"""PRA-177 generator checks that do not build the full circuits."""

import numpy as np

from tasks.dfthcsos.checks import acceptance_problems
from tasks.dfthcsos.generate import batch_deltas
from tasks.dfthcsos.gates import g1_smoke as dfthc_smoke
from tasks.dqi.gates import g1_smoke as dqi_smoke


def test_batch_deltas_xor_schedule():
    words = np.array([[1, 2, 3, 4], [5, 6, 7, 8]], dtype=np.int64)
    deltas = batch_deltas(words, 3)
    assert deltas.shape == (2, 2, 3)
    assert np.array_equal(deltas[0], np.array([[1, 2, 3], [5, 6, 7]]))
    assert np.array_equal(deltas[1], np.array([[4, 0, 0], [8, 0, 0]]) ^ np.array([[1, 2, 3], [5, 6, 7]]))


def test_acceptance_floors():
    good = {"error_1": 0.003, "error_2": 0.018, "Lambda": 308.0, "E_gap": 3.96, "gap_in_domain": True}
    assert acceptance_problems(good) == []
    low_gap = dict(good, E_gap=3.914898)
    assert any("E_gap" in item for item in acceptance_problems(low_gap))
    low_lambda = dict(good, Lambda=49.0)
    assert any("Lambda" in item for item in acceptance_problems(low_lambda))
    bad_error = dict(good, error_2=0.021)
    assert any("error_2" in item for item in acceptance_problems(bad_error))


def test_smoke_builders():
    assert dfthc_smoke(None)["status"] == "PASS"
    assert dqi_smoke(None)["status"] == "PASS"
