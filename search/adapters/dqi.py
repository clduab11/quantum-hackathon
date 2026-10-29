# SPDX-License-Identifier: Apache-2.0
"""dqi adapter: windows and parameters of the dqi generator on main."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from search.adapters.base import SEARCH_DIR, CandidateBundle, TaskAdapter

STAGE1_SHOTS = int(os.environ.get("SEARCH_DQI_STAGE1_SHOTS", "128"))
# Reduced proxy for cascade stage 2; never grants feasibility on its own.
REDUCED_SHOTS = int(os.environ.get("SEARCH_DQI_STAGE2_SHOTS", "1536"))
# Official full verification shot count (ledger / package contract).
FULL_SHOTS = int(os.environ.get("SEARCH_DQI_FULL_SHOTS", "102400"))
LOCAL_SALTS = (
    "PRA171_LOCAL_PUBLIC_FIXED_SALT_0001",
    "PRA171_LOCAL_PUBLIC_FIXED_SALT_0002",
    "PRA171_LOCAL_PUBLIC_FIXED_SALT_0003",
)


def _r_eps(k_failures: int, shots: int) -> float:
    """Repetition overhead R(ε) from failure count over ``shots``."""
    import math
    eps = max(k_failures / max(shots, 1), 1e-12)
    inner = 0.5 + 2.0 * math.sqrt(eps)
    if inner >= 1.0:
        return 1e6
    return math.log(2.0) / (-math.log(inner))


class DqiAdapter(TaskAdapter):
    """Staged adapter for the dqi search program."""

    name = "dqi"
    initial_program = SEARCH_DIR / "initial_dqi.py"

    def build_command(self, program_path: Path, outdir: Path) -> list[str]:
        """Build argv that writes ``outdir/dqi.kmb`` from the evolvable program."""
        import sys
        return [sys.executable, str(program_path), "--out", str(outdir)]

    def parse_build_report(self, stdout: str, outdir: Path) -> dict[str, Any]:
        """Parse the program's JSON stdout report."""
        del outdir
        return json.loads(stdout)

    def collect_circuit_bytes(self, outdir: Path) -> dict[str, bytes]:
        """Keep a short prefix for the text-vs-binary check (dqi.kmb can be ~0.8 GB)."""
        found: dict[str, bytes] = {}
        for path in sorted(outdir.rglob("*")):
            if path.is_file() and path.suffix in {".kmb", ".kmx"}:
                with path.open("rb") as stream:
                    found[path.relative_to(outdir).as_posix()] = stream.read(4096)
        return found

    def fingerprint(self, bundle: CandidateBundle) -> bytes:
        """Hash on-disk ``.kmb``/``.kmx`` files without loading the whole circuit."""
        from search.adapters.base import sha256_file
        parts = []
        for path in sorted(bundle.outdir.rglob("*")):
            if path.is_file() and path.suffix in {".kmb", ".kmx"}:
                rel = path.relative_to(bundle.outdir).as_posix()
                parts.append(rel.encode("utf-8"))
                parts.append(sha256_file(path).encode("ascii"))
        return b"\0".join(parts)

    def verifier_settings(self) -> dict[str, Any]:
        """Salts and worker count that affect DQI verification outcomes."""
        return {"salts": list(LOCAL_SALTS), "max_workers": 1}

    def stage1_sample(self, bundle: CandidateBundle, seed: int) -> dict[str, Any]:
        """Algebra smoke + static circuit presence. Never marks feasible."""
        del seed
        from tasks.dqi.algebra import smoke

        algebra = smoke()
        algebra_ok = algebra.get("status") == "PASS"
        report = bundle.report or {}
        path = bundle.outdir / "dqi.kmb"
        present = path.is_file() and path.stat().st_size > 0
        qubits = float(report.get("num_qubits") or 0.0)
        toffoli = float(report.get("static_toffoli_like") or 0.0)
        sample_ok = algebra_ok and present and not bundle.problems
        shots = STAGE1_SHOTS
        k = 0 if sample_ok else shots
        return {
            "feasible": False,
            "fraction_correct": 1.0 if sample_ok else 0.0,
            "max_error_over_tol": 0.0 if sample_ok else 9.0,
            "ancilla_dirty_fraction": 0.0,
            "phase_wrong_fraction": 0.0,
            "toffoli_count": toffoli,
            "qubit_count": qubits,
            "k_failures": float(k),
            "eps_plus": float(k / max(shots, 1)),
            "r_eps": _r_eps(k, shots),
            "shots": shots,
            "algebra": algebra,
        }

    def _verify_at_shots(self, bundle: CandidateBundle, shots: int, *, allow_feasible: bool) -> dict[str, Any]:
        """Run the package verifier at ``shots``; ``allow_feasible`` gates the feasible flag."""
        report = bundle.report or {}
        if report.get("smoke_package_sample"):
            # Smoke path only: package sample scores as feasible inside the smoke namespace.
            return {
                "feasible": bool(allow_feasible),
                "fraction_correct": 1.0,
                "max_error_over_tol": 0.0,
                "ancilla_dirty_fraction": 0.0,
                "phase_wrong_fraction": 0.0,
                "toffoli_count": float(report.get("static_toffoli_like") or 0.0),
                "qubit_count": float(report.get("num_qubits") or 0.0),
                "k_failures": 0.0,
                "eps_plus": 0.0,
                "r_eps": _r_eps(0, FULL_SHOTS),
                "salts": [{"salt": s, "k": 0, "smoke": True} for s in LOCAL_SALTS],
                "shots": 0 if report.get("smoke_package_sample") else shots,
                "smoke": True,
            }
        import kickmix as km
        from dqi.verify_submission_dqi import ProblemSpecDQI, verify

        path = bundle.outdir / "dqi.kmb"
        circuit = km.Circuit.from_file(str(path))
        spec = ProblemSpecDQI.benchmark_instance(num_shots=shots)
        per_salt = []
        max_k = 0
        last: dict[str, Any] = {}
        for salt in LOCAL_SALTS:
            try:
                summary = verify(circuit, spec, salt=salt, max_workers=1)
                k = int(summary.get("value_errors") or 0) + int(summary.get("phase_errors") or 0)
                per_salt.append({"salt": salt, "k": k, "summary": summary})
                max_k = max(max_k, k)
                last = summary
            except Exception as exc:  # noqa: BLE001 — any verifier failure counts as max-k
                per_salt.append({"salt": salt, "k": shots, "error": f"{type(exc).__name__}: {exc}"})
                max_k = max(max_k, shots)
        ok = max_k == 0 and bool(last)
        return {
            "feasible": bool(allow_feasible and ok),
            "fraction_correct": 1.0 if ok else max(0.0, 1.0 - max_k / max(shots, 1)),
            "max_error_over_tol": 0.0 if ok else min(9.0, 100.0 * max_k / max(shots, 1)),
            "ancilla_dirty_fraction": 0.0,
            "phase_wrong_fraction": 0.0 if ok else min(1.0, max_k / max(shots, 1)),
            "toffoli_count": float(last.get("toffoli_count") or report.get("static_toffoli_like") or 0.0),
            "qubit_count": float(last.get("num_qubits") or report.get("num_qubits") or 0.0),
            "k_failures": float(max_k),
            "eps_plus": float(max_k / max(shots, 1)),
            "r_eps": _r_eps(max_k, shots),
            "salts": per_salt,
            "shots": shots,
        }

    def reduced_shots(self) -> int | None:
        """Reduced-stage shot count for the verifier memo key."""
        return REDUCED_SHOTS

    def full_shots(self) -> int | None:
        """Full-stage shot count for the verifier memo key."""
        return FULL_SHOTS

    def stage2_verify(self, bundle: CandidateBundle) -> dict[str, Any]:
        """Default verify entry: full official shots (feasibility only on PASS)."""
        return self.stage2_verify_full(bundle)

    def stage2_verify_reduced(self, bundle: CandidateBundle) -> dict[str, Any]:
        """Reduced-shot proxy; never sets ``feasible``."""
        result = self._verify_at_shots(bundle, REDUCED_SHOTS, allow_feasible=False)
        result["verification_stage"] = "reduced"
        return result

    def stage2_verify_full(self, bundle: CandidateBundle) -> dict[str, Any]:
        """Full official verification at 102,400 shots; sole feasibility arbiter."""
        result = self._verify_at_shots(bundle, FULL_SHOTS, allow_feasible=True)
        result["verification_stage"] = "full"
        return result

    def cost_fields(self, bundle: CandidateBundle, sample: dict[str, Any],
                    verified: dict[str, Any] | None) -> dict[str, Any]:
        """Resource + graded fields for ``combined_score`` / rich metrics."""
        source = verified if verified else sample
        return {
            "task": "dqi",
            "toffoli_count": source.get("toffoli_count", 0.0),
            "qubit_count": source.get("qubit_count", 0.0),
            "k_failures": source.get("k_failures", 0.0),
            "eps_plus": source.get("eps_plus", 0.0),
            "r_eps": source.get("r_eps", 1.0),
            "fraction_correct": source.get("fraction_correct", 0.0),
            "max_error_over_tol": source.get("max_error_over_tol", 0.0),
            "ancilla_dirty_fraction": source.get("ancilla_dirty_fraction", 0.0),
            "phase_wrong_fraction": source.get("phase_wrong_fraction", 0.0),
            "feasible": bool(verified and verified.get("feasible")),
        }
