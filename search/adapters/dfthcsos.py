# SPDX-License-Identifier: Apache-2.0
"""dfthcsos adapter: compiler + brot/J/B/C knobs via the existing initial_program."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import yaml

from search.adapters.base import SEARCH_DIR, CandidateBundle, DEFAULT_DATA, TaskAdapter, sha256_file

NUM_ANGLES = 75
QUBIT_CAP = 128


class DfthcsosAdapter(TaskAdapter):
    name = "dfthcsos"
    initial_program = SEARCH_DIR / "initial_program.py"

    def stage0_build(self, program_path: Path, outdir: Path | None = None,
                     timeout: float = 420.0) -> CandidateBundle:
        """Build the chemistry family, with a smoke package-sample shortcut."""
        if os.environ.get("SEARCH_SMOKE") == "1":
            import shutil
            import tempfile
            from search.adapters.base import sha256_file

            out = Path(outdir or tempfile.mkdtemp(prefix=f"{self.task}-eval-"))
            bundle = CandidateBundle(task=self.task, program_path=program_path, outdir=out)
            bundle.problems.extend(self.stage0_parse(program_path))
            if bundle.problems:
                return bundle
            src = DEFAULT_DATA / "sample_submission" / "dfthcsos"
            dest = out / "dfthcsos"
            shutil.copytree(src, dest)
            # Reference family resources (Google sample); avoid loading 10 .kmb files in smoke.
            circuits = [{"num_qubits": 119, "num_instructions": 280_000, "toffoli_like_static": 3974, "z_pow": 0}
                        for _ in range(10)]
            bundle.report = {
                "task": "dfthcsos",
                "smoke_package_sample": True,
                "circuits": circuits,
                "batch_size": 8,
                "brot": 12,
                "num_circuits": 10,
                "max_qubits": 119,
                "rows": 3976,
                "files": {
                    f"dfthcsos/angle_k_{k}.kmb": {"sha256": sha256_file(dest / f"angle_k_{k}.kmb")}
                    for k in range(10)
                },
            }
            bundle.circuit_bytes = self.collect_circuit_bytes(out)
            bundle.problems.extend(self.static_checks(bundle))
            return bundle
        return super().stage0_build(program_path, outdir=outdir, timeout=timeout)

    def factor_config(self) -> dict[str, Any]:
        """Load and hash-check the declared factorization input."""
        path = Path(os.environ.get("SEARCH_FACTOR_CONFIG", SEARCH_DIR / "factor.yaml"))
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        os.environ.setdefault("VQCC_DATA", str(DEFAULT_DATA))
        factor = Path(os.path.expandvars(str(raw["factorization"])))
        if not factor.is_file():
            raise FileNotFoundError(f"declared factor file is missing: {factor}")
        digest = sha256_file(factor)
        if digest != str(raw["sha256"]):
            raise ValueError(f"declared factor {factor} has SHA-256 {digest}, pinned {raw['sha256']}")
        return {"path": factor, "sha256": digest, "source_brot": int(raw.get("source_brot", 12))}

    def build_command(self, program_path: Path, outdir: Path) -> list[str]:
        import sys
        cfg = self.factor_config()
        return [
            sys.executable, str(program_path),
            "--out", str(outdir),
            "--factorization", str(cfg["path"]),
            "--source-brot", str(cfg["source_brot"]),
        ]

    def parse_build_report(self, stdout: str, outdir: Path) -> dict[str, Any]:
        del outdir
        return json.loads(stdout)

    def static_checks(self, bundle: CandidateBundle) -> list[str]:
        """Enforce dfthcsos layout, qubit cap, and required output files."""
        problems = super().static_checks(bundle)
        report = bundle.report or {}
        circuits = report.get("circuits") or []
        if not circuits:
            problems.append("report lists no circuits")
            return problems
        batch_size = int(report.get("batch_size") or 0)
        if batch_size < 1:
            problems.append("report has no batch_size")
        else:
            expected = math.ceil(NUM_ANGLES / batch_size)
            if len(circuits) != expected:
                problems.append(f"J={batch_size} needs {expected} circuits, program wrote {len(circuits)}")
        if any(int(c.get("num_qubits", 0)) > QUBIT_CAP for c in circuits):
            problems.append(f"a circuit exceeds the {QUBIT_CAP}-qubit verifier cap")
        if any(int(c.get("z_pow", 0)) for c in circuits):
            problems.append("Z_POW rotations are rejected by the verifier")
        expected_files = {f"dfthcsos/angle_k_{k}.kmb" for k in range(math.ceil(NUM_ANGLES / max(batch_size, 1)))}
        expected_files.add("dfthcsos/submission.npz")
        missing = sorted(expected_files - {p.relative_to(bundle.outdir).as_posix()
                                           for p in bundle.outdir.rglob("*") if p.is_file()})
        if missing:
            problems.append(f"missing output files: {missing}")
        return problems

    def submission_identity(self, bundle: CandidateBundle) -> str:
        """SHA-256 of the chemistry ``submission.npz`` when present."""
        path = bundle.outdir / "dfthcsos" / "submission.npz"
        if path.is_file():
            return sha256_file(path)
        return ""

    def stage1_sample(self, bundle: CandidateBundle, seed: int) -> dict[str, Any]:
        """Cheap static G2 proxy + seeded shot subsample; never marks feasible."""
        del seed  # dfthcsos proxy is deterministic; seed reserved for future shot sampling
        report = bundle.report or {}
        # Bundle flag alone controls smoke shortcuts (not the process env).
        if report.get("smoke_package_sample"):
            circuits = report.get("circuits") or []
            t = float(sum(int(c.get("toffoli_like_static") or 0) for c in circuits))
            q = float(sum(int(c.get("num_qubits") or 0) for c in circuits))
            return {
                "feasible": False,
                "fraction_correct": 1.0 if circuits and not bundle.problems else 0.0,
                "max_error_over_tol": 0.0,
                "ancilla_dirty_fraction": 0.0,
                "phase_wrong_fraction": 0.0,
                "toffoli_count": t,
                "qubit_count": q,
                "lambda_eff": 48.764,
                "error_1": 0.0,
                "error_2": 0.0,
                "proxy": {"status": "PASS", "smoke": True},
            }
        from tasks.dfthcsos.gates import g2_proxy

        proxy = g2_proxy(bundle.outdir)
        status = str(proxy.get("status", "FAIL"))
        ok = status == "PASS"
        t = float(proxy.get("estimated_toffoli") or 0.0)
        q = float(proxy.get("estimated_qubits") or 0.0)
        return {
            "feasible": False,
            "fraction_correct": 1.0 if ok else 0.0,
            "max_error_over_tol": 0.0 if ok else 9.0,
            "ancilla_dirty_fraction": 0.0,
            "phase_wrong_fraction": 0.0,
            "toffoli_count": t,
            "qubit_count": q,
            "lambda_eff": float(proxy.get("lambda_eff") or 0.0),
            "error_1": float(proxy.get("error_1") or 0.0),
            "error_2": float(proxy.get("error_2") or 0.0),
            "proxy": proxy,
        }

    def stage2_verify_reduced(self, bundle: CandidateBundle) -> dict[str, Any]:
        """Reduced-shot official verify; never sets ``feasible``."""
        report = bundle.report or {}
        if report.get("smoke_package_sample"):
            sample = self.stage1_sample(bundle, seed=0)
            ok = sample.get("fraction_correct", 0.0) >= 1.0
            return {
                "feasible": False,
                "fraction_correct": sample.get("fraction_correct", 0.0),
                "max_error_over_tol": sample.get("max_error_over_tol", 0.0),
                "ancilla_dirty_fraction": 0.0,
                "phase_wrong_fraction": 0.0,
                "toffoli_count": sample.get("toffoli_count", 0.0),
                "qubit_count": sample.get("qubit_count", 0.0),
                "lambda_eff": sample.get("lambda_eff", 48.0),
                "error_1": sample.get("error_1", 0.0),
                "error_2": sample.get("error_2", 0.0),
                "E_gap": 0.0,
                "verifier": {"status": "PASS" if ok else "FAIL", "smoke": True, "stage": "reduced"},
                "verification_stage": "reduced",
                "reduced_pass": ok,
            }
        from search import evaluator as ev

        chemistry = bundle.outdir / "dfthcsos"
        result = ev.verify_family_isolated(chemistry, ev.REDUCED_SHOTS)
        pass_ok = result.get("status") == "PASS"
        metrics = result.get("metrics") or {}
        return {
            "feasible": False,
            "fraction_correct": 0.99 if pass_ok else 0.0,
            "max_error_over_tol": 1.0,
            "ancilla_dirty_fraction": 0.0,
            "phase_wrong_fraction": 0.0,
            "toffoli_count": float(result.get("toffoli_count") or 0.0),
            "qubit_count": float(result.get("num_qubits") or 0.0),
            "lambda_eff": float(result.get("lambda_eff") or 0.0),
            "error_1": float(metrics.get("error_1") or 0.0),
            "error_2": float(metrics.get("error_2") or 0.0),
            "E_gap": float(metrics.get("E_gap") or metrics.get("e_gap") or 0.0),
            "verifier": result,
            "verification_stage": "reduced",
            "reduced_pass": pass_ok,
        }

    def stage2_verify_full(self, bundle: CandidateBundle) -> dict[str, Any]:
        """Full official verify (64 shots/address); sole feasibility arbiter."""
        report = bundle.report or {}
        if report.get("smoke_package_sample"):
            sample = self.stage1_sample(bundle, seed=0)
            ok = sample.get("fraction_correct", 0.0) >= 1.0
            return {
                "feasible": ok,
                "fraction_correct": sample.get("fraction_correct", 0.0),
                "max_error_over_tol": sample.get("max_error_over_tol", 0.0),
                "ancilla_dirty_fraction": 0.0,
                "phase_wrong_fraction": 0.0,
                "toffoli_count": sample.get("toffoli_count", 0.0),
                "qubit_count": sample.get("qubit_count", 0.0),
                "lambda_eff": sample.get("lambda_eff", 48.0),
                "error_1": sample.get("error_1", 0.0),
                "error_2": sample.get("error_2", 0.0),
                "E_gap": 0.0,
                "verifier": {"status": "PASS" if ok else "FAIL", "smoke": True, "stage": "full"},
                "verification_stage": "full",
            }
        from search import evaluator as ev

        chemistry = bundle.outdir / "dfthcsos"
        result = ev.verify_family_isolated(chemistry, ev.FULL_SHOTS)
        pass_ok = result.get("status") == "PASS"
        metrics = result.get("metrics") or {}
        return {
            "feasible": pass_ok,
            "fraction_correct": 1.0 if pass_ok else 0.0,
            "max_error_over_tol": 0.0 if pass_ok else 9.0,
            "ancilla_dirty_fraction": 0.0,
            "phase_wrong_fraction": 0.0,
            "toffoli_count": float(result.get("toffoli_count") or 0.0),
            "qubit_count": float(result.get("num_qubits") or 0.0),
            "lambda_eff": float(result.get("lambda_eff") or 0.0),
            "error_1": float(metrics.get("error_1") or 0.0),
            "error_2": float(metrics.get("error_2") or 0.0),
            "E_gap": float(metrics.get("E_gap") or metrics.get("e_gap") or 0.0),
            "verifier": result,
            "verification_stage": "full",
        }

    def reduced_shots(self) -> int | None:
        """Reduced-stage shot count for the verifier memo key."""
        from search import evaluator as ev
        return ev.REDUCED_SHOTS

    def full_shots(self) -> int | None:
        """Full-stage shot count for the verifier memo key."""
        from search import evaluator as ev
        return ev.FULL_SHOTS

    def stage2_verify(self, bundle: CandidateBundle) -> dict[str, Any]:
        """Default verify entry delegates to the full official path."""
        return self.stage2_verify_full(bundle)

    def cost_fields(self, bundle: CandidateBundle, sample: dict[str, Any],
                    verified: dict[str, Any] | None) -> dict[str, Any]:
        """Map sample/verify outputs into Deb-layered fitness fields."""
        source = verified if verified else sample
        return {
            "task": "dfthcsos",
            "toffoli_count": source.get("toffoli_count", 0.0),
            "qubit_count": source.get("qubit_count", 0.0),
            "lambda_eff": source.get("lambda_eff", 1.0),
            "error_1": source.get("error_1", 0.0),
            "error_2": source.get("error_2", 0.0),
            "E_gap": source.get("E_gap", 0.0),
            "fraction_correct": source.get("fraction_correct", 0.0),
            "max_error_over_tol": source.get("max_error_over_tol", 0.0),
            "ancilla_dirty_fraction": source.get("ancilla_dirty_fraction", 0.0),
            "phase_wrong_fraction": source.get("phase_wrong_fraction", 0.0),
            "feasible": bool(verified and verified.get("feasible")),
        }
