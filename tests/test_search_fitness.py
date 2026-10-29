# SPDX-License-Identifier: Apache-2.0
"""Dense Deb-layered fitness, memo and private stage-1 seed (PRA-315)."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from search.fitness import combined_score, feasible_score, graded_violation, task_log_cost
from search.memo import VerifierMemo
from search.stage_seed import STAGE1_SEED, generation_seed, seed_in_text


REPO = Path(__file__).resolve().parents[1]
PROMPTS = REPO / "search" / "prompts"


def _feasible(task: str, **kwargs):
    base = {
        "feasible": True,
        "task": task,
        "toffoli_count": 1000.0,
        "qubit_count": 64.0,
        "fraction_correct": 1.0,
        "max_error_over_tol": 0.0,
        "ancilla_dirty_fraction": 0.0,
        "phase_wrong_fraction": 0.0,
        "cost_c": 1000.0,
        "lambda_eff": 50.0,
        "r_eps": 1.1,
    }
    base.update(kwargs)
    return base


def test_infeasible_below_half_feasible_at_or_above():
    bad = {
        "feasible": False,
        "fraction_correct": 0.0,
        "max_error_over_tol": 9.0,
        "ancilla_dirty_fraction": 1.0,
        "phase_wrong_fraction": 1.0,
    }
    good = _feasible("invsqrt")
    assert combined_score(bad) < 0.5 <= combined_score(good, task="invsqrt")
    # A near-perfect but unverified sample must still lose to any feasible circuit.
    almost = {
        "feasible": False,
        "fraction_correct": 0.999,
        "max_error_over_tol": 0.0,
        "ancilla_dirty_fraction": 0.0,
        "phase_wrong_fraction": 0.0,
    }
    assert combined_score(almost) < 0.5 <= combined_score(good, task="dfthcsos")


@pytest.mark.parametrize("task,term,kwargs", [
    ("invsqrt", "qubit_count", {"cost_c": 1700.0}),
    ("invsqrt", "cost_c", {"qubit_count": 63.0}),
    ("dqi", "toffoli_count", {"qubit_count": 889.0, "r_eps": 1.05}),
    ("dqi", "qubit_count", {"toffoli_count": 474308.0, "r_eps": 1.05}),
    ("dqi", "r_eps", {"toffoli_count": 474308.0, "qubit_count": 889.0}),
    ("dfthcsos", "toffoli_count", {"qubit_count": 430.0, "lambda_eff": 48.0}),
    ("dfthcsos", "qubit_count", {"toffoli_count": 16366.0, "lambda_eff": 48.0}),
    ("dfthcsos", "lambda_eff", {"toffoli_count": 16366.0, "qubit_count": 430.0}),
])
def test_feasible_score_monotone_in_each_log_cost_term(task, term, kwargs):
    low = _feasible(task, **{**kwargs, term: 100.0 if term != "r_eps" and term != "lambda_eff" else 1.05})
    high = _feasible(task, **{**kwargs, term: 200.0 if term != "r_eps" and term != "lambda_eff" else 2.1})
    # Larger resource / R → larger log cost → lower score.
    assert task_log_cost(task, low) < task_log_cost(task, high)
    assert combined_score(low, task=task) > combined_score(high, task=task)


def test_graded_violation_uses_the_max_of_four_terms():
    res = {
        "fraction_correct": 0.5,          # violation 0.5
        "max_error_over_tol": 3.0,        # clip(2,0,9) = 2
        "ancilla_dirty_fraction": 0.1,
        "phase_wrong_fraction": 0.25,
    }
    assert graded_violation(res) == pytest.approx(2.0)


def test_byte_identical_circuits_hit_the_memo():
    memo = VerifierMemo()
    payload = {"status": "PASS", "k_failures": 0, "seconds": 1.2}
    first = memo.get_or_set(b"circuit-bytes", lambda: dict(payload))
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return {"status": "FAIL", "k_failures": 99}

    second = memo.get_or_set(b"circuit-bytes", factory)
    assert first == second == payload
    assert calls["n"] == 0
    assert memo.hits == 1 and memo.misses == 1


def test_stage1_seed_is_fixed_per_generation_and_absent_from_prompts():
    assert generation_seed(0) == STAGE1_SEED
    assert generation_seed(7) != generation_seed(8)
    # The private seed must never appear in anything the model reads.
    blobs = [
        (PROMPTS / "system_message.txt").read_text(encoding="utf-8"),
        (PROMPTS / "diff_user.txt").read_text(encoding="utf-8"),
        (REPO / "search" / "DISCOVERY.md").read_text(encoding="utf-8"),
    ]
    for text in blobs:
        assert not seed_in_text(text), "stage-1 seed leaked into a prompt artifact"
    assert seed_in_text(f"generation seed is {STAGE1_SEED}")


def test_feasible_band_ends_at_one():
    perfect = feasible_score(5.0, log_min=5.0, log_max=40.0)
    worst = feasible_score(40.0, log_min=5.0, log_max=40.0)
    assert perfect == pytest.approx(1.0)
    assert worst == pytest.approx(0.5)
    assert math.isfinite(combined_score(_feasible("invsqrt"), task="invsqrt"))
