# SPDX-License-Identifier: Apache-2.0
"""PRA-331 fix-list regression tests (routing, memo, smoke, cascade, fitness)."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from search.adapters.base import CandidateBundle
from search.adapters.dqi import DqiAdapter, FULL_SHOTS, REDUCED_SHOTS
from search.adapters.invsqrt import InvsqrtAdapter
from search.evaluate_entry import _backend, _task
from search.fitness import combined_score
from search.memo import VerifierMemo, settings_digest, verification_key
from search import evaluator as ev


REPO = Path(__file__).resolve().parents[1]
SEARCH = REPO / "search"


# --- item 5: cascade-gate disagreement ---------------------------------------------------------


def _fake_build(program_path: str) -> ev.Build:
    build = ev.Build(
        program_path=program_path,
        program_sha256="a" * 64,
        outdir=Path("/tmp/fake-outdir"),
        chemistry=Path("/tmp/fake-outdir/dfthcsos"),
    )
    build.report = {
        "circuits": [{"num_qubits": 10}], "batch_size": 8,
        "num_circuits": 1, "brot": 12, "max_qubits": 10,
    }
    build.proxy = {
        "predicted_ratio": 1.0, "estimated_toffoli": 1000,
        "estimated_qubits": 64, "status": "PASS",
    }
    build.problems = []
    build.seconds = 0.1
    build.stage_seconds = {"stage1": 0.1}
    return build


def test_a_stage3_is_entered_for_reduced_pass_candidate(monkeypatch, tmp_path):
    """(a) A reduced-shot PASS that should reach stage 3 must invoke the full verifier."""
    monkeypatch.setenv("SEARCH_SCRATCH", str(tmp_path))
    monkeypatch.setenv("SEARCH_KEEP_OUTPUTS", "1")
    build = _fake_build(str(tmp_path / "prog.py"))
    (tmp_path / "prog.py").write_text("# dummy\n", encoding="utf-8")
    stage3_calls = {"n": 0}

    def fake_verify(chemistry, shots, timeout=None):
        if shots == ev.REDUCED_SHOTS:
            return {
                "status": "PASS", "shots_per_address": shots, "ratio": 1.1,
                "toffoli_count": 1000.0, "num_qubits": 64, "lambda_eff": 48.0,
                "metrics": {"error_1": 0.0, "error_2": 0.0}, "seconds": 0.01,
            }
        stage3_calls["n"] += 1
        return {
            "status": "PASS", "shots_per_address": shots, "ratio": 1.1,
            "toffoli_count": 1000.0, "num_qubits": 64, "lambda_eff": 48.0,
            "metrics": {"error_1": 0.0, "error_2": 0.0}, "seconds": 0.02,
        }

    monkeypatch.setattr(ev, "_build_for", lambda p: (ev._BUILDS.__setitem__(str(p), build) or build))
    monkeypatch.setattr(ev, "verify_family_isolated", fake_verify)
    monkeypatch.setattr(ev, "discard", lambda b: None)
    monkeypatch.setattr(ev, "record_evaluation", lambda *a, **k: None)

    result = ev.evaluate(str(tmp_path / "prog.py"))
    assert stage3_calls["n"] >= 1, (
        f"stage 3 never called; combined_score={result.metrics['combined_score']!r}; "
        f"STAGE2_THRESHOLD={ev.STAGE2_THRESHOLD!r}"
    )


def test_b_reduced_pass_alone_never_sets_feasible(monkeypatch, tmp_path):
    """(b) A reduced-shot PASS alone must never mark the candidate feasible."""
    monkeypatch.setenv("SEARCH_SCRATCH", str(tmp_path))
    monkeypatch.setenv("SEARCH_KEEP_OUTPUTS", "1")
    build = _fake_build(str(tmp_path / "prog.py"))
    (tmp_path / "prog.py").write_text("# dummy\n", encoding="utf-8")

    def fake_verify(chemistry, shots, timeout=None):
        assert shots == ev.REDUCED_SHOTS
        return {
            "status": "PASS", "shots_per_address": shots, "ratio": 1.1,
            "toffoli_count": 1000.0, "num_qubits": 64, "lambda_eff": 48.0,
            "metrics": {"error_1": 0.0, "error_2": 0.0}, "seconds": 0.01,
        }

    monkeypatch.setattr(ev, "_build_for", lambda p: (ev._BUILDS.__setitem__(str(p), build) or build))
    monkeypatch.setattr(ev, "verify_family_isolated", fake_verify)
    monkeypatch.setattr(ev, "discard", lambda b: None)
    monkeypatch.setattr(ev, "record_evaluation", lambda *a, **k: None)

    result = ev.evaluate_stage2(str(tmp_path / "prog.py"))
    assert result.metrics["feasible"] == 0.0
    assert result.metrics["combined_score"] < 0.5
    assert ev.score_policy(True, 1.1, {"status": "PASS", "ratio": 1.1}, None) < 0.5


# --- item 1: live routing ----------------------------------------------------------------------


@pytest.mark.parametrize("task,module_name", [
    ("dfthcsos", "evaluator"),
    ("invsqrt", "adapter_cascade"),
    ("dqi", "adapter_cascade"),
])
def test_live_routing_selects_task_specific_evaluator(monkeypatch, task, module_name):
    """Live OpenEvolve entry routes each task to the correct evaluator backend."""
    monkeypatch.setenv("SEARCH_TASK", task)
    assert _task() == task
    backend, resolved = _backend()
    assert resolved == task
    assert backend.__name__.endswith(module_name)
    for name in ("evaluate_stage1", "evaluate_stage2", "evaluate_stage3", "evaluate"):
        assert callable(getattr(backend, name))


def test_run_points_openevolve_at_evaluate_entry():
    """``search.run`` must hand OpenEvolve the routing entry, not chemistry-only."""
    text = (SEARCH / "run.py").read_text(encoding="utf-8")
    assert "evaluate_entry.py" in text
    assert 'evaluation_file=str(SEARCH_DIR / "evaluator.py")' not in text


# --- items 2–3: memo key + smoke isolation -----------------------------------------------------


def test_memo_misses_when_task_changes():
    memo = VerifierMemo()
    fp = b"circuit-a"
    k1 = verification_key(task="invsqrt", mode="full", circuit_fingerprint=fp, shots=64)
    k2 = verification_key(task="dqi", mode="full", circuit_fingerprint=fp, shots=64)
    memo.set(k1, {"status": "PASS"})
    assert memo.get(k2) is None


def test_memo_misses_when_mode_changes_smoke_vs_full():
    """Smoke-derived results live in a separate namespace from full verification."""
    memo = VerifierMemo()
    fp = b"circuit-a"
    smoke = verification_key(task="dfthcsos", mode="smoke", circuit_fingerprint=fp, shots=2)
    full = verification_key(task="dfthcsos", mode="full", circuit_fingerprint=fp, shots=2)
    memo.set(smoke, {"status": "PASS", "feasible": True, "smoke": True})
    assert memo.get(full) is None
    assert memo.get(smoke)["smoke"] is True


def test_memo_misses_when_shots_change():
    memo = VerifierMemo()
    fp = b"circuit-a"
    k1 = verification_key(task="dfthcsos", mode="full", circuit_fingerprint=fp, shots=2)
    k2 = verification_key(task="dfthcsos", mode="full", circuit_fingerprint=fp, shots=64)
    memo.set(k1, {"status": "PASS"})
    assert memo.get(k2) is None


def test_memo_misses_when_verifier_settings_change():
    memo = VerifierMemo()
    fp = b"circuit-a"
    s1 = settings_digest({"salt": "A"})
    s2 = settings_digest({"salt": "B"})
    k1 = verification_key(task="dqi", mode="full", circuit_fingerprint=fp, shots=102400,
                          verifier_settings=s1)
    k2 = verification_key(task="dqi", mode="full", circuit_fingerprint=fp, shots=102400,
                          verifier_settings=s2)
    memo.set(k1, {"status": "PASS"})
    assert memo.get(k2) is None


def test_memo_misses_when_dfthcsos_submission_identity_changes():
    memo = VerifierMemo()
    fp = b"circuit-a"
    k1 = verification_key(task="dfthcsos", mode="full", circuit_fingerprint=fp, shots=64,
                          submission_id="aaa")
    k2 = verification_key(task="dfthcsos", mode="full", circuit_fingerprint=fp, shots=64,
                          submission_id="bbb")
    memo.set(k1, {"status": "PASS"})
    assert memo.get(k2) is None


def test_smoke_pass_cannot_satisfy_full_verification_request():
    """Explicit isolation: a smoke hit must not be returned for a full key."""
    memo = VerifierMemo()
    fp = b"same-bytes"
    smoke_key = verification_key(task="invsqrt", mode="smoke", circuit_fingerprint=fp, shots=0)
    full_key = verification_key(task="invsqrt", mode="full", circuit_fingerprint=fp, shots=0)
    memo.set(smoke_key, {"feasible": True, "status": "PASS"})
    assert memo.get(full_key) is None


# --- item 4: DQI reduced vs full ---------------------------------------------------------------


def test_dqi_reduced_never_sets_feasible(tmp_path, monkeypatch):
    adapter = DqiAdapter()
    bundle = CandidateBundle(task="dqi", program_path=tmp_path / "p.py", outdir=tmp_path)
    bundle.report = {"num_qubits": 10, "static_toffoli_like": 100}

    def fake_verify(bundle, shots, *, allow_feasible):
        return {
            "feasible": allow_feasible,  # adapter must still force False on reduced
            "fraction_correct": 1.0,
            "shots": shots,
            "k_failures": 0.0,
            "eps_plus": 0.0,
            "r_eps": 1.0,
            "toffoli_count": 100.0,
            "qubit_count": 10.0,
            "max_error_over_tol": 0.0,
            "ancilla_dirty_fraction": 0.0,
            "phase_wrong_fraction": 0.0,
        }

    monkeypatch.setattr(adapter, "_verify_at_shots", fake_verify)
    reduced = adapter.stage2_verify_reduced(bundle)
    assert reduced["feasible"] is False
    assert reduced["shots"] == REDUCED_SHOTS
    assert reduced["verification_stage"] == "reduced"


def test_dqi_full_verifier_stage_is_reachable_and_uses_official_shots(tmp_path, monkeypatch):
    adapter = DqiAdapter()
    bundle = CandidateBundle(task="dqi", program_path=tmp_path / "p.py", outdir=tmp_path)
    bundle.report = {"num_qubits": 10, "static_toffoli_like": 100}
    seen = {"shots": None, "allow": None}

    def fake_verify(bundle, shots, *, allow_feasible):
        seen["shots"] = shots
        seen["allow"] = allow_feasible
        return {
            "feasible": allow_feasible,
            "fraction_correct": 1.0,
            "shots": shots,
            "k_failures": 0.0,
            "eps_plus": 0.0,
            "r_eps": 1.0,
            "toffoli_count": 100.0,
            "qubit_count": 10.0,
            "max_error_over_tol": 0.0,
            "ancilla_dirty_fraction": 0.0,
            "phase_wrong_fraction": 0.0,
        }

    monkeypatch.setattr(adapter, "_verify_at_shots", fake_verify)
    full = adapter.stage2_verify_full(bundle)
    assert seen["shots"] == FULL_SHOTS == 102400
    assert seen["allow"] is True
    assert full["feasible"] is True
    assert full["verification_stage"] == "full"


# --- item 6: dense fitness for unverified ------------------------------------------------------


def test_dense_fitness_ignores_cost_for_infeasible_same_violation():
    """Confirm CodeRabbit merge-risk: infeasible scores ignore resource cost (Deb design)."""
    low = {
        "feasible": False, "fraction_correct": 0.5, "max_error_over_tol": 1.0,
        "ancilla_dirty_fraction": 0.0, "phase_wrong_fraction": 0.0,
        "toffoli_count": 10.0, "qubit_count": 8.0,
    }
    high = dict(low, toffoli_count=1_000_000.0, qubit_count=800.0)
    assert combined_score(low) == pytest.approx(combined_score(high))


def test_static_only_candidates_differ_by_predicted_ratio():
    """After the max_error fix, different predicted ratios yield different scores."""
    low = ev.score_policy(True, 0.1, None, None)
    high = ev.score_policy(True, 1.0, None, None)
    assert low < high < 0.5


def test_lambda_eff_missing_or_zero_cannot_improve_feasible_score():
    from search.fitness import task_log_cost
    base = {
        "feasible": True, "task": "dfthcsos",
        "toffoli_count": 1000.0, "qubit_count": 64.0, "lambda_eff": 50.0,
    }
    missing = dict(base, lambda_eff=0.0)
    assert task_log_cost("dfthcsos", missing) >= task_log_cost("dfthcsos", {**base, "lambda_eff": 1.0})


# --- invsqrt reduced never feasible ------------------------------------------------------------


def test_invsqrt_reduced_never_sets_feasible(tmp_path):
    """Smoke package-sample reduced path never grants feasibility."""
    adapter = InvsqrtAdapter()
    bundle = CandidateBundle(task="invsqrt", program_path=tmp_path / "p.py", outdir=tmp_path)
    bundle.report = {
        "smoke_package_sample": True,
        "expected_toffoli": 100.0,
        "qubits": 22.0,
        "cost_c": 100.0,
    }
    reduced = adapter.stage2_verify_reduced(bundle)
    assert reduced["feasible"] is False
    assert reduced["verification_stage"] == "reduced"
