# SPDX-License-Identifier: Apache-2.0
"""PRA-334 fix-list regression tests (PRA-333's 7 defects on PR #75)."""
from __future__ import annotations

import os
import traceback
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from search.adapters.base import CandidateBundle, TaskAdapter
from search.adapters.dfthcsos import DfthcsosAdapter
from search.adapters.dqi import DqiAdapter, FULL_SHOTS as DQI_FULL, REDUCED_SHOTS as DQI_REDUCED
from search.adapters.invsqrt import InvsqrtAdapter
from search import adapter_cascade as cascade
from search import evaluator as ev
from search import staged
from search.memo import VerifierMemo, settings_digest, verification_key


REPO = Path(__file__).resolve().parents[1]


def _bundle(tmp_path: Path, task: str, *, report: dict | None = None) -> CandidateBundle:
    out = tmp_path / f"{task}-out"
    out.mkdir(exist_ok=True)
    (out / "marker.txt").write_text("alive", encoding="utf-8")
    return CandidateBundle(
        task=task,
        program_path=tmp_path / "prog.py",
        outdir=out,
        report=report or {},
        circuit_bytes={"x.kmb": b"\x00binary"},
    )


def _recording_adapter(task: str, bundle: CandidateBundle, *,
                       sample_fc: float, reduced_fc: float,
                       full_feasible: bool = True) -> MagicMock:
    adapter = MagicMock(spec=TaskAdapter)
    adapter.task = task
    adapter.name = task
    adapter.stage0_build.return_value = bundle
    adapter.stage1_sample.return_value = {
        "feasible": False,
        "fraction_correct": sample_fc,
        "max_error_over_tol": 0.0 if sample_fc >= 1.0 else 9.0,
        "ancilla_dirty_fraction": 0.0,
        "phase_wrong_fraction": 0.0,
        "toffoli_count": 100.0,
        "qubit_count": 10.0,
        "cost_c": 100.0,
        "r_eps": 1.0,
        "k_failures": 0.0,
        "eps_plus": 0.0,
    }

    def cost_fields(bundle, sample, verified):
        source = verified if verified else sample
        return {
            "task": task,
            "toffoli_count": source.get("toffoli_count", 0.0),
            "qubit_count": source.get("qubit_count", 0.0),
            "cost_c": source.get("cost_c", source.get("toffoli_count", 0.0)),
            "r_eps": source.get("r_eps", 1.0),
            "k_failures": source.get("k_failures", 0.0),
            "eps_plus": source.get("eps_plus", 0.0),
            "fraction_correct": source.get("fraction_correct", 0.0),
            "max_error_over_tol": source.get("max_error_over_tol", 0.0),
            "ancilla_dirty_fraction": source.get("ancilla_dirty_fraction", 0.0),
            "phase_wrong_fraction": source.get("phase_wrong_fraction", 0.0),
            "feasible": bool(verified and verified.get("feasible")),
        }

    adapter.cost_fields.side_effect = cost_fields
    adapter.fingerprint.return_value = b"fp"
    adapter.verifier_settings.return_value = {}
    adapter.submission_identity.return_value = ""
    adapter.reduced_shots.return_value = 1536 if task == "dqi" else None
    adapter.full_shots.return_value = 102400 if task == "dqi" else None

    adapter.stage2_verify_reduced.return_value = {
        "feasible": False,
        "fraction_correct": reduced_fc,
        "max_error_over_tol": 0.0 if reduced_fc >= 1.0 else 9.0,
        "ancilla_dirty_fraction": 0.0,
        "phase_wrong_fraction": 0.0,
        "toffoli_count": 100.0,
        "qubit_count": 10.0,
        "cost_c": 100.0,
        "r_eps": 1.0,
        "verification_stage": "reduced",
        "reduced_pass": reduced_fc >= 1.0,
    }
    adapter.stage2_verify_full.return_value = {
        "feasible": full_feasible,
        "fraction_correct": 1.0 if full_feasible else 0.0,
        "max_error_over_tol": 0.0 if full_feasible else 9.0,
        "ancilla_dirty_fraction": 0.0,
        "phase_wrong_fraction": 0.0,
        "toffoli_count": 100.0,
        "qubit_count": 10.0,
        "cost_c": 100.0,
        "r_eps": 1.0,
        "verification_stage": "full",
    }
    return adapter


# --- defect 1: reduced result drives stage-2 score ---------------------------------------------


@pytest.mark.parametrize("task", ["invsqrt", "dqi"])
def test_reduced_zero_blocks_full_verify(task, tmp_path, monkeypatch):
    """Reduced fraction_correct=0 must stop the cascade before stage2_verify_full."""
    cascade._STATE.clear()
    cascade._MEMO = VerifierMemo()
    bundle = _bundle(tmp_path, task)
    adapter = _recording_adapter(task, bundle, sample_fc=1.0, reduced_fc=0.0)
    monkeypatch.setattr(cascade, "_adapter_for", lambda t, generation=0: adapter)

    result = cascade.evaluate(str(tmp_path / "prog.py"), task=task)
    adapter.stage2_verify_full.assert_not_called()
    assert result.metrics["feasible"] == 0.0
    assert result.metrics["combined_score"] < 0.5


@pytest.mark.parametrize("task", ["invsqrt", "dqi"])
def test_reduced_pass_reaches_full_even_when_sample_is_zero(task, tmp_path, monkeypatch):
    """Reduced fraction_correct=1.0 must call full verify even if stage-1 sample is 0."""
    cascade._STATE.clear()
    cascade._MEMO = VerifierMemo()
    bundle = _bundle(tmp_path, task)
    adapter = _recording_adapter(task, bundle, sample_fc=0.0, reduced_fc=1.0, full_feasible=True)
    monkeypatch.setattr(cascade, "_adapter_for", lambda t, generation=0: adapter)

    result = cascade.evaluate(str(tmp_path / "prog.py"), task=task)
    adapter.stage2_verify_full.assert_called_once()
    # feasible stays 0 until the full result is in — and full was called; after full it may be 1.
    assert result.metrics["feasible"] == 1.0
    assert result.metrics["stage_reached"] == 3.0


def test_cost_fields_use_verified_even_when_not_feasible():
    """Adapter cost_fields must prefer any verified result over the stage-1 sample."""
    for Adapter in (InvsqrtAdapter, DqiAdapter, DfthcsosAdapter):
        adapter = Adapter()
        sample = {
            "fraction_correct": 1.0, "max_error_over_tol": 0.0,
            "ancilla_dirty_fraction": 0.0, "phase_wrong_fraction": 0.0,
            "toffoli_count": 1.0, "qubit_count": 1.0, "cost_c": 1.0,
            "r_eps": 1.0, "lambda_eff": 1.0, "error_1": 0.0, "error_2": 0.0, "E_gap": 0.0,
            "k_failures": 0.0, "eps_plus": 0.0, "margin_min": 0.0,
        }
        verified = {
            "feasible": False, "fraction_correct": 0.0, "max_error_over_tol": 9.0,
            "ancilla_dirty_fraction": 0.0, "phase_wrong_fraction": 0.0,
            "toffoli_count": 50.0, "qubit_count": 8.0, "cost_c": 50.0,
            "r_eps": 2.0, "lambda_eff": 2.0, "error_1": 0.1, "error_2": 0.1, "E_gap": 0.0,
            "k_failures": 1.0, "eps_plus": 0.1, "margin_min": 0.0,
            "verification_stage": "reduced",
        }
        bundle = CandidateBundle(task=adapter.name, program_path=Path("p.py"), outdir=Path("."))
        fields = adapter.cost_fields(bundle, sample, verified)
        assert fields["fraction_correct"] == 0.0
        assert fields["feasible"] is False


# --- defect 2: build-dir leak ------------------------------------------------------------------


def test_adapter_cascade_cleans_outdir_on_stage1_fail(tmp_path, monkeypatch):
    cascade._STATE.clear()
    cascade._MEMO = VerifierMemo()
    bundle = _bundle(tmp_path, "invsqrt")
    outdir = bundle.outdir
    adapter = _recording_adapter("invsqrt", bundle, sample_fc=0.0, reduced_fc=0.0)
    # Force a stage-1 score below STAGE1_THRESHOLD via problems.
    bundle.problems = ["forced failure"]
    monkeypatch.setattr(cascade, "_adapter_for", lambda t, generation=0: adapter)

    result = cascade.evaluate(str(tmp_path / "prog.py"), task="invsqrt")
    assert result.metrics["combined_score"] < cascade.STAGE1_THRESHOLD
    assert not outdir.exists()
    assert cascade._STATE == {}


def test_adapter_cascade_cleans_outdir_on_stage2_fail(tmp_path, monkeypatch):
    cascade._STATE.clear()
    cascade._MEMO = VerifierMemo()
    bundle = _bundle(tmp_path, "invsqrt")
    outdir = bundle.outdir
    adapter = _recording_adapter("invsqrt", bundle, sample_fc=1.0, reduced_fc=0.0)
    monkeypatch.setattr(cascade, "_adapter_for", lambda t, generation=0: adapter)

    result = cascade.evaluate(str(tmp_path / "prog.py"), task="invsqrt")
    assert result.metrics["combined_score"] < cascade.STAGE2_THRESHOLD
    assert not outdir.exists()
    assert cascade._STATE == {}


def test_adapter_cascade_cleans_outdir_after_stage3(tmp_path, monkeypatch):
    cascade._STATE.clear()
    cascade._MEMO = VerifierMemo()
    bundle = _bundle(tmp_path, "invsqrt")
    outdir = bundle.outdir
    adapter = _recording_adapter("invsqrt", bundle, sample_fc=1.0, reduced_fc=1.0)
    monkeypatch.setattr(cascade, "_adapter_for", lambda t, generation=0: adapter)

    result = cascade.evaluate(str(tmp_path / "prog.py"), task="invsqrt")
    assert result.metrics["stage_reached"] == 3.0
    assert not outdir.exists()
    assert cascade._STATE == {}


# --- defect 3: exceptions escape ---------------------------------------------------------------


def test_adapter_cascade_stage_swallows_exception_and_cleans(tmp_path, monkeypatch):
    cascade._STATE.clear()
    cascade._MEMO = VerifierMemo()
    outdir = tmp_path / "built"
    outdir.mkdir()
    (outdir / "x").write_text("y", encoding="utf-8")

    class BoomAdapter(TaskAdapter):
        name = "invsqrt"

        def stage0_build(self, program_path, outdir=None, timeout=420.0):
            return CandidateBundle(
                task="invsqrt", program_path=program_path, outdir=outdir,
                circuit_bytes={"a.kmb": b"\x00"},
            )

        def stage1_sample(self, bundle, seed):
            raise RuntimeError("boom in sample")

        def cost_fields(self, bundle, sample, verified):
            return {"task": "invsqrt", "feasible": False, "fraction_correct": 0.0,
                    "max_error_over_tol": 9.0, "ancilla_dirty_fraction": 0.0,
                    "phase_wrong_fraction": 0.0, "toffoli_count": 1.0, "qubit_count": 1.0}

    adapter = BoomAdapter()
    # Pre-seed state as stage0 would, then explode in sample via evaluate_stage1's path.
    # Easier: make stage0_build raise after creating outdir ownership through evaluate_stage1.
    def boom_build(program):
        bundle = CandidateBundle(task="invsqrt", program_path=program, outdir=outdir)
        cascade._STATE[cascade._state_key(str(program), "invsqrt")] = {
            "bundle": bundle, "sample": None, "reduced": None, "verified": None,
            "adapter_task": "invsqrt",
        }
        raise RuntimeError("boom in build")

    adapter = MagicMock(spec=TaskAdapter)
    adapter.task = "invsqrt"
    adapter.stage0_build.side_effect = boom_build
    monkeypatch.setattr(cascade, "_adapter_for", lambda t, generation=0: adapter)

    result = cascade.evaluate_stage1(str(tmp_path / "prog.py"), task="invsqrt")
    assert result.metrics["combined_score"] == 0.0
    assert "evaluator_traceback" in result.artifacts
    assert "RuntimeError" in result.artifacts["evaluator_traceback"]
    assert not outdir.exists()
    assert cascade._STATE == {}


# --- defect 4: stale SEARCH_SMOKE --------------------------------------------------------------


def test_invsqrt_stage1_ignores_stale_search_smoke(tmp_path, monkeypatch):
    """SEARCH_SMOKE alone must not trigger the structural smoke sample shortcut."""
    monkeypatch.setenv("SEARCH_SMOKE", "1")
    adapter = InvsqrtAdapter()
    bundle = _bundle(tmp_path, "invsqrt", report={
        "qubits": 22.0, "expected_toffoli": 100.0, "cost_c": 100.0, "margin_units": 1.0,
    })
    # Without smoke_package_sample the integer model path runs (or fails importing tables).
    # Spy on the smoke branch by ensuring we do not take the early structural return:
    # if SEARCH_SMOKE still gated, fraction_correct would be 1.0 with sample_size set and
    # no need for tables. Force the non-smoke path to be detectable via monkeypatch.
    called = {"model": False}

    def fake_model(*a, **k):
        called["model"] = True
        import numpy as np
        return np.zeros(len(a[0]) if a else 1, dtype=np.uint64)

    monkeypatch.setattr("tasks.invsqrt.signed_digit.integer_model", fake_model, raising=False)
    monkeypatch.setattr(
        "tasks.invsqrt.signed_digit.load_or_build_tables",
        lambda: (SimpleNamespace(fy=10), {}, None),
        raising=False,
    )
    # Import path inside stage1_sample is local; patch the module after ensuring import works.
    import tasks.invsqrt.signed_digit as sd
    monkeypatch.setattr(sd, "integer_model", fake_model)
    monkeypatch.setattr(sd, "load_or_build_tables", lambda: (SimpleNamespace(fy=10), {}, None))

    sample = adapter.stage1_sample(bundle, seed=0)
    assert called["model"] is True
    assert "smoke" not in str(sample.get("verifier", {}))


# --- defect 5: memo binds shots ----------------------------------------------------------------


def test_adapters_expose_shot_counts():
    assert DqiAdapter().reduced_shots() == DQI_REDUCED
    assert DqiAdapter().full_shots() == DQI_FULL
    assert DfthcsosAdapter().reduced_shots() == ev.REDUCED_SHOTS
    assert DfthcsosAdapter().full_shots() == ev.FULL_SHOTS
    assert InvsqrtAdapter().reduced_shots() is None
    assert InvsqrtAdapter().full_shots() is None


def test_adapter_cascade_memo_misses_when_shot_count_changes(tmp_path, monkeypatch):
    """Changing the adapter's reduced shot count must miss the cascade memo."""
    cascade._STATE.clear()
    cascade._MEMO = VerifierMemo()
    bundle = _bundle(tmp_path, "dqi")
    adapter = _recording_adapter("dqi", bundle, sample_fc=1.0, reduced_fc=1.0)
    adapter.reduced_shots.return_value = 1536
    adapter.full_shots.return_value = 102400
    monkeypatch.setattr(cascade, "_adapter_for", lambda t, generation=0: adapter)

    cascade.evaluate_stage1(str(tmp_path / "prog.py"), task="dqi")
    cascade.evaluate_stage2(str(tmp_path / "prog.py"), task="dqi")
    assert adapter.stage2_verify_reduced.call_count == 1

    # Same fingerprint, different shot binding → miss.
    adapter.reduced_shots.return_value = 9999
    cascade.evaluate_stage2(str(tmp_path / "prog.py"), task="dqi")
    assert adapter.stage2_verify_reduced.call_count == 2


def test_staged_has_no_dead_memo_key_line():
    text = (REPO / "search" / "staged.py").read_text(encoding="utf-8")
    assert "reduced_key = _memo_key(" not in text


# --- defect 6: invsqrt counts from measured circuit --------------------------------------------


def test_g2_proxy_pass_includes_static_counts(monkeypatch, tmp_path):
    from tasks.invsqrt import gates

    smoke = {
        "status": "PASS", "sha256": "abc", "static_toffoli": 1234, "num_qubits": 22,
    }
    monkeypatch.setattr(gates, "g1_smoke", lambda d: smoke)
    monkeypatch.setattr(gates, "run_mirror", lambda: {"pass": True, "min_margin_units": 1})
    proxy = gates.g2_proxy(tmp_path)
    assert proxy["static_toffoli"] == 1234
    assert proxy["num_qubits"] == 22


def test_invsqrt_report_cannot_undercut_measured_counts(tmp_path, monkeypatch):
    """A candidate report claiming smaller counts than the circuit must not win."""
    adapter = InvsqrtAdapter()
    bundle = _bundle(tmp_path, "invsqrt", report={
        "expected_toffoli": 10.0,  # lies low
        "qubits": 4.0,
        "cost_c": 10.0,
        "margin_units": 1.0,
    })

    def fake_proxy(outdir):
        return {
            "status": "PASS",
            "sha256": "x",
            "static_toffoli": 5000,
            "num_qubits": 22,
            "min_margin_units": 1.0,
            "estimated_expected_cost": 5000.0,
        }

    monkeypatch.setattr("tasks.invsqrt.gates.g2_proxy", fake_proxy)
    reduced = adapter.stage2_verify_reduced(bundle)
    full = adapter.stage2_verify_full(bundle)
    assert reduced["toffoli_count"] == 5000.0
    assert reduced["qubit_count"] == 22.0
    assert full["toffoli_count"] == 5000.0
    assert full["qubit_count"] == 22.0


# --- defect 7: smoke exit code -----------------------------------------------------------------


def test_run_smoke_returns_one_on_problems(monkeypatch):
    from search import run as search_run

    # Claim SEARCH_SMOKE / VQCC_DATA before run_smoke writes them, so teardown restores.
    monkeypatch.setenv("SEARCH_SMOKE", "0")
    monkeypatch.setenv("VQCC_DATA", search_run.DEFAULT_DATA)
    monkeypatch.setattr(
        "search.staged.smoke_evaluate",
        lambda task, repeats=1: {
            "median_seconds": {"stage0": 0.1, "stage1": 0.1, "stage3": 0.1, "stages_0_1_3": 0.3},
            "combined_score": 0.0,
            "problems": ["build failed"],
        },
    )
    assert search_run.run_smoke("invsqrt") == 1
