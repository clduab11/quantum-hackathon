# SPDX-License-Identifier: Apache-2.0
"""PRA-336 fix-list regression tests (CodeRabbit's 4 threads on fa531065)."""
from __future__ import annotations

from pathlib import Path

from search.adapters.base import CandidateBundle
from search.adapters.invsqrt import InvsqrtAdapter
from search import adapter_cascade as cascade


REPO = Path(__file__).resolve().parents[1]


def _bundle(tmp_path: Path, *, report: dict | None = None) -> CandidateBundle:
    out = tmp_path / "invsqrt-out"
    out.mkdir(exist_ok=True)
    (out / "marker.txt").write_text("alive", encoding="utf-8")
    return CandidateBundle(
        task="invsqrt",
        program_path=tmp_path / "prog.py",
        outdir=out,
        report=report or {},
        circuit_bytes={"invsqrt.kmb": b"\x00binary"},
    )


# --- item 1: _failed_result summary carries exception type/message -----------------------------


def test_failed_result_summary_includes_exception_type_and_message(tmp_path):
    result = cascade._failed_result(
        str(tmp_path / "prog.py"), "dqi", 2, ValueError("boom")
    )
    summary = result.artifacts["summary"]
    assert "ValueError" in summary
    assert "boom" in summary
    assert "not the program's fault" not in summary
    assert "evaluator_traceback" in result.artifacts
    assert result.metrics["combined_score"] == 0.0


# --- item 2: cost_c from measured mirror estimate, not candidate report ------------------------


def test_invsqrt_cost_c_from_mirror_estimate_not_report(tmp_path, monkeypatch):
    """A candidate under-reporting cost_c must not win on either verify path."""
    adapter = InvsqrtAdapter()
    bundle = _bundle(tmp_path, report={
        "cost_c": 1.0,
        "expected_toffoli": 1.0,
        "qubits": 4.0,
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
    assert reduced["cost_c"] == 5000.0
    assert full["cost_c"] == 5000.0


def test_run_mirror_returns_estimated_expected_cost(monkeypatch):
    """Mirror must surface the canonical estimate key from compilation_report."""
    from tasks.invsqrt import mirror as mirror_mod

    fake_built = {
        "phase": {"phase_match": True},
        "calibration": {"margin_units": 1, "worst_x": 1},
        "final": {
            "qubits": 22,
            "static_toffoli": 100,
            "expected_toffoli": 100,
            "rotations": 1,
        },
        "estimate": {"estimated_expected_cost": 1234.5, "ratio": 1.0},
        "sha256": "abc",
        "coefficient_provenance": "test",
        "circuit_authorship": "port",
    }
    monkeypatch.setattr(mirror_mod, "load_or_build_tables", lambda: ({}, {}, 0.0))
    monkeypatch.setattr(
        mirror_mod,
        "exhaustive_certificate",
        lambda cfg, tables: {
            "pass": True,
            "tested_inputs": 1,
            "worst_ratio": 0.0,
            "worst_x": 1,
            "min_margin_units": 1,
            "phase_fraction_bits": 64,
            "first_bad_x": None,
        },
    )
    monkeypatch.setattr(mirror_mod, "_derivative_reference", lambda flag: object())
    monkeypatch.setattr(
        mirror_mod,
        "prepare_derivative_split",
        lambda ref, cfg, tables: (
            None,
            {"normalized_addresses_checked": mirror_mod.NORMALIZED_PAIRS},
        ),
    )
    monkeypatch.setattr(
        mirror_mod,
        "layout",
        lambda cfg, tables: {"w1": 18, "LB": 21, "S": 20, "whi": 8},
    )
    monkeypatch.setattr(
        "tasks.invsqrt.generate.compilation_report", lambda: fake_built
    )
    report = mirror_mod.run_mirror()
    assert "estimated_expected_cost" in report
    assert report["estimated_expected_cost"] == 1234.5

