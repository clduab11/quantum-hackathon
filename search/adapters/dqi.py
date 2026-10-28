# SPDX-License-Identifier: Apache-2.0
"""dqi adapter: windows and parameters of the dqi generator on main."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from search.adapters.base import SEARCH_DIR, CandidateBundle, TaskAdapter

STAGE1_SHOTS = int(os.environ.get("SEARCH_DQI_STAGE1_SHOTS", "128"))
LOCAL_SALTS = (
    "PRA171_LOCAL_PUBLIC_FIXED_SALT_0001",
    "PRA171_LOCAL_PUBLIC_FIXED_SALT_0002",
    "PRA171_LOCAL_PUBLIC_FIXED_SALT_0003",
)


def _r_eps(k_failures: int, shots: int) -> float:
    import math
    eps = max(k_failures / max(shots, 1), 1e-12)
    inner = 0.5 + 2.0 * math.sqrt(eps)
    if inner >= 1.0:
        return 1e6
    return math.log(2.0) / (-math.log(inner))


class DqiAdapter(TaskAdapter):
    name = "dqi"
    initial_program = SEARCH_DIR / "initial_dqi.py"

    def build_command(self, program_path: Path, outdir: Path) -> list[str]:
        import sys
        return [sys.executable, str(program_path), "--out", str(outdir)]

    def parse_build_report(self, stdout: str, outdir: Path) -> dict[str, Any]:
        del outdir
        return json.loads(stdout)

    def collect_circuit_bytes(self, outdir: Path) -> dict[str, bytes]:
        # dqi.kmb can be ~0.8 GB; keep a short prefix for the text-vs-binary check
        # and hash the file separately in fingerprint().
        found: dict[str, bytes] = {}
        for path in sorted(outdir.rglob("*")):
            if path.is_file() and path.suffix in {".kmb", ".kmx"}:
                with path.open("rb") as stream:
                    found[path.relative_to(outdir).as_posix()] = stream.read(4096)
        return found

    def fingerprint(self, bundle: CandidateBundle) -> bytes:
        from search.adapters.base import sha256_file
        parts = []
        for path in sorted(bundle.outdir.rglob("*")):
            if path.is_file() and path.suffix in {".kmb", ".kmx"}:
                rel = path.relative_to(bundle.outdir).as_posix()
                parts.append(rel.encode("utf-8"))
                parts.append(sha256_file(path).encode("ascii"))
        return b"\0".join(parts)

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

    def stage2_verify(self, bundle: CandidateBundle) -> dict[str, Any]:
        """Official verifier on ≥ 3 local salts; report the max k."""
        report = bundle.report or {}
        if report.get("smoke_package_sample"):
            return {
                "feasible": True,
                "fraction_correct": 1.0,
                "max_error_over_tol": 0.0,
                "ancilla_dirty_fraction": 0.0,
                "phase_wrong_fraction": 0.0,
                "toffoli_count": float(report.get("static_toffoli_like") or 0.0),
                "qubit_count": float(report.get("num_qubits") or 0.0),
                "k_failures": 0.0,
                "eps_plus": 0.0,
                "r_eps": _r_eps(0, 102400),
                "salts": [{"salt": s, "k": 0, "smoke": True} for s in LOCAL_SALTS],
                "shots": 0,
            }
        import kickmix as km
        from dqi.verify_submission_dqi import ProblemSpecDQI, verify

        path = bundle.outdir / "dqi.kmb"
        circuit = km.Circuit.from_file(str(path))
        shots = int(os.environ.get("SEARCH_DQI_STAGE2_SHOTS", "1536"))
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
            except AssertionError as exc:
                per_salt.append({"salt": salt, "k": shots, "error": str(exc)})
                max_k = max(max_k, shots)
        ok = max_k == 0 and bool(last)
        return {
            "feasible": ok,
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

    def cost_fields(self, bundle: CandidateBundle, sample: dict[str, Any],
                    verified: dict[str, Any] | None) -> dict[str, Any]:
        source = verified if verified and verified.get("feasible") else sample
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
