# SPDX-License-Identifier: Apache-2.0
"""invsqrt adapter: schedule and coefficient knobs in tasks/invsqrt/."""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from search.adapters.base import SEARCH_DIR, CandidateBundle, TaskAdapter

# Boundary classes from the research report §6.2 (lexicase classes).
BOUNDARY_X = (1, 2, 4, 8, 16, 33, 58, 70, 76, 85, 107, 112, 116, 120, 2**20, 3_133_452)
SAMPLE_SIZE = 4096


class InvsqrtAdapter(TaskAdapter):
    name = "invsqrt"
    initial_program = SEARCH_DIR / "initial_invsqrt.py"

    def build_command(self, program_path: Path, outdir: Path) -> list[str]:
        """Build argv that writes ``outdir/invsqrt.kmb``."""
        import sys
        return [sys.executable, str(program_path), "--out", str(outdir)]

    def parse_build_report(self, stdout: str, outdir: Path) -> dict[str, Any]:
        """Parse the program's JSON stdout report."""
        del outdir
        return json.loads(stdout)

    def stage1_sample(self, bundle: CandidateBundle, seed: int) -> dict[str, Any]:
        """Seeded subset of the integer arithmetic, including boundary classes."""
        import math
        import os
        import numpy as np

        report = bundle.report or {}
        qubits = float(report.get("qubits") or 0.0)
        toffoli = float(report.get("expected_toffoli") or report.get("static_toffoli") or 0.0)
        cost_c = float(report.get("cost_c") or toffoli)
        margin = float(report.get("margin_units") or 0.0)
        rng = random.Random(seed)
        xs = set(BOUNDARY_X)
        max_x = 3_133_452
        while len(xs) < SAMPLE_SIZE:
            xs.add(rng.randint(1, max_x))
        ordered = np.array(sorted(xs), dtype=np.int64)
        if report.get("smoke_package_sample"):
            # Smoke: structural sample only (package sample is the reference circuit).
            return {
                "feasible": False,
                "fraction_correct": 1.0 if bundle.circuit_bytes and not bundle.problems else 0.0,
                "max_error_over_tol": 0.0,
                "ancilla_dirty_fraction": 0.0,
                "phase_wrong_fraction": 0.0,
                "toffoli_count": toffoli,
                "qubit_count": qubits,
                "cost_c": cost_c,
                "margin_min": margin,
                "sample_size": int(len(ordered)),
            }
        from tasks.invsqrt.signed_digit import integer_model, load_or_build_tables

        cfg, tables, _ = load_or_build_tables()
        output_fraction = cfg.fy + 10
        values = integer_model(ordered, cfg, tables).astype(np.uint64)
        phase = values << np.uint64(64 - output_fraction)
        roots = [math.isqrt((1 << 130) // int(x)) for x in ordered]
        target = np.array([((r + 1) >> 1) & ((1 << 64) - 1) for r in roots], dtype=np.uint64)
        tolerance = np.array([min(r >> 25, 1 << 63) for r in roots], dtype=np.uint64)
        error = np.abs((phase - target).view(np.int64)).view(np.uint64)
        ratio = error.astype(np.float64) / np.maximum(tolerance.astype(np.float64), 1.0)
        failures = int(np.count_nonzero(error > tolerance))
        worst = float(ratio.max()) if len(ratio) else 0.0
        passed = failures == 0
        return {
            "feasible": False,
            "fraction_correct": 1.0 - failures / max(len(ordered), 1),
            "max_error_over_tol": 0.0 if passed else max(worst, 1.0),
            "ancilla_dirty_fraction": 0.0,
            "phase_wrong_fraction": 0.0,
            "toffoli_count": toffoli,
            "qubit_count": qubits,
            "cost_c": cost_c,
            "margin_min": margin,
            "sample_size": int(len(ordered)),
        }

    def stage2_verify_reduced(self, bundle: CandidateBundle) -> dict[str, Any]:
        """G2 integer-mirror proxy; never sets ``feasible``."""
        report = bundle.report or {}
        if report.get("smoke_package_sample"):
            return {
                "feasible": False,
                "fraction_correct": 1.0,
                "max_error_over_tol": 0.0,
                "ancilla_dirty_fraction": 0.0,
                "phase_wrong_fraction": 0.0,
                "toffoli_count": float(report.get("expected_toffoli") or 0.0),
                "qubit_count": float(report.get("qubits") or 0.0),
                "cost_c": float(report.get("cost_c") or report.get("expected_toffoli") or 0.0),
                "margin_min": float(report.get("margin_units") or 0.0),
                "verifier": {"status": "PASS", "smoke": True, "stage": "reduced"},
                "verification_stage": "reduced",
            }
        from tasks.invsqrt.gates import g2_proxy

        proxy = g2_proxy(bundle.outdir)
        ok = str(proxy.get("status")) == "PASS"
        return {
            "feasible": False,
            "fraction_correct": 1.0 if ok else 0.0,
            "max_error_over_tol": 0.0 if ok else 9.0,
            "ancilla_dirty_fraction": 0.0,
            "phase_wrong_fraction": 0.0,
            "toffoli_count": float(proxy.get("static_toffoli") or report.get("expected_toffoli") or 0.0),
            "qubit_count": float(proxy.get("num_qubits") or report.get("qubits") or 0.0),
            "cost_c": float(report.get("cost_c") or report.get("expected_toffoli") or 0.0),
            "margin_min": float(report.get("margin_units") or proxy.get("min_margin_units") or 0.0),
            "verifier": proxy,
            "verification_stage": "reduced",
            "reduced_pass": ok,
        }

    def stage2_verify_full(self, bundle: CandidateBundle) -> dict[str, Any]:
        """Full official-style verify (G2 mirror stands in for the package verifier gate).

        Feasibility is granted only here (or on the smoke package-sample path inside
        the smoke memo namespace). Reduced-shot / G2-proxy success alone never does.
        """
        report = bundle.report or {}
        if report.get("smoke_package_sample"):
            return {
                "feasible": True,
                "fraction_correct": 1.0,
                "max_error_over_tol": 0.0,
                "ancilla_dirty_fraction": 0.0,
                "phase_wrong_fraction": 0.0,
                "toffoli_count": float(report.get("expected_toffoli") or 0.0),
                "qubit_count": float(report.get("qubits") or 0.0),
                "cost_c": float(report.get("cost_c") or report.get("expected_toffoli") or 0.0),
                "margin_min": float(report.get("margin_units") or 0.0),
                "verifier": {"status": "PASS", "smoke": True, "stage": "full"},
                "verification_stage": "full",
            }
        from tasks.invsqrt.gates import g2_proxy

        proxy = g2_proxy(bundle.outdir)
        ok = str(proxy.get("status")) == "PASS"
        return {
            "feasible": ok,
            "fraction_correct": 1.0 if ok else 0.0,
            "max_error_over_tol": 0.0 if ok else 9.0,
            "ancilla_dirty_fraction": 0.0,
            "phase_wrong_fraction": 0.0,
            "toffoli_count": float(proxy.get("static_toffoli") or report.get("expected_toffoli") or 0.0),
            "qubit_count": float(proxy.get("num_qubits") or report.get("qubits") or 0.0),
            "cost_c": float(report.get("cost_c") or report.get("expected_toffoli") or 0.0),
            "margin_min": float(report.get("margin_units") or proxy.get("min_margin_units") or 0.0),
            "verifier": proxy,
            "verification_stage": "full",
        }

    def stage2_verify(self, bundle: CandidateBundle) -> dict[str, Any]:
        """Default verify entry delegates to the full official-style path."""
        return self.stage2_verify_full(bundle)

    def cost_fields(self, bundle: CandidateBundle, sample: dict[str, Any],
                    verified: dict[str, Any] | None) -> dict[str, Any]:
        """Map sample/verify outputs into Deb-layered fitness fields."""
        source = verified if verified else sample
        return {
            "task": "invsqrt",
            "toffoli_count": source.get("toffoli_count", 0.0),
            "qubit_count": source.get("qubit_count", 0.0),
            "cost_c": source.get("cost_c", source.get("toffoli_count", 0.0)),
            "margin_min": source.get("margin_min", 0.0),
            "fraction_correct": source.get("fraction_correct", 0.0),
            "max_error_over_tol": source.get("max_error_over_tol", 0.0),
            "ancilla_dirty_fraction": source.get("ancilla_dirty_fraction", 0.0),
            "phase_wrong_fraction": source.get("phase_wrong_fraction", 0.0),
            "feasible": bool(verified and verified.get("feasible")),
        }
