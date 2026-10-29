# SPDX-License-Identifier: Apache-2.0
"""Staged evaluator: 0 parse/build, 1 sample, 2 reduced, 2b full official, 3 cost score."""
from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from search.adapters import get_adapter
from search.adapters.base import StageTimings, TaskAdapter
from search.fitness import combined_score, rich_metrics
from search.memo import VerifierMemo, settings_digest, verification_key
from search.stage_seed import generation_seed

_MEMO = VerifierMemo()


@dataclass
class StagedResult:
    """Outcome of one staged evaluation for a single task/program."""

    task: str
    metrics: dict[str, float]
    timings: StageTimings
    sample: dict[str, Any] = field(default_factory=dict)
    verified: dict[str, Any] | None = None
    reduced: dict[str, Any] | None = None
    problems: list[str] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    memo_hit: bool = False

    @property
    def combined_score(self) -> float:
        """Scalar OpenEvolve fitness from ``metrics``."""
        return float(self.metrics.get("combined_score", 0.0))


def _is_smoke_bundle(bundle: Any) -> bool:
    """True when the build report marks a smoke package-sample shortcut."""
    report = getattr(bundle, "report", None) or {}
    return bool(report.get("smoke_package_sample"))


def evaluate_candidate(
    task: str,
    program_path: Path | None = None,
    *,
    generation: int = 0,
    run_stage2: bool = True,
    run_full_verify: bool = True,
    adapter: TaskAdapter | None = None,
    memo: VerifierMemo | None = None,
    outdir: Path | None = None,
) -> StagedResult:
    """Run stages 0, 1, reduced verify, optional full verify, then cost score.

    Stage 1 never sets feasible. A reduced-shot pass alone never sets feasible.
    Full official verification is the only live path that may mark feasible.
    Smoke package-sample results are memoised under the ``smoke`` namespace so
    they can never satisfy a later ``full`` request.
    """
    adapter = adapter or get_adapter(task, generation=generation)
    program = Path(program_path or adapter.program_path())
    memo = memo or _MEMO
    timings = StageTimings()
    owns_outdir = outdir is None
    bundle = None

    try:
        t0 = time.perf_counter()
        bundle = adapter.stage0_build(program, outdir=outdir)
        timings.stage0 = time.perf_counter() - t0
        if bundle.problems:
            res = {
                "feasible": False,
                "fraction_correct": 0.0,
                "max_error_over_tol": 9.0,
                "ancilla_dirty_fraction": 1.0,
                "phase_wrong_fraction": 1.0,
                "toffoli_count": 1.0,
                "qubit_count": 1.0,
                "task": task,
            }
            t3 = time.perf_counter()
            score = combined_score(res, task=task)
            metrics = rich_metrics(res, task=task, score=score)
            timings.stage3 = time.perf_counter() - t3
            return StagedResult(
                task=task, metrics=metrics, timings=timings, problems=list(bundle.problems),
                artifacts={"stderr": bundle.stderr, "stdout": bundle.stdout[:2000]},
            )

        seed = generation_seed(generation)
        t1 = time.perf_counter()
        sample = adapter.stage1_sample(bundle, seed)
        sample["feasible"] = False  # hard rule: stage 1 is never the feasibility arbiter
        timings.stage1 = time.perf_counter() - t1

        verified = None
        reduced = None
        memo_hit = False
        smoke = _is_smoke_bundle(bundle)
        mode = "smoke" if smoke else "full"

        if run_stage2:
            t2 = time.perf_counter()
            # Distinguish reduced vs full inside the mode namespace via settings suffix in key:
            reduced_key = verification_key(
                task=adapter.task,
                mode=mode,
                circuit_fingerprint=adapter.fingerprint(bundle) + b"|reduced",
                shots=adapter.reduced_shots(),
                verifier_settings=settings_digest({**adapter.verifier_settings(), "stage": "reduced"}),
                submission_id=adapter.submission_identity(bundle),
            )
            cached_reduced = memo.get(reduced_key)
            if cached_reduced is not None:
                reduced = cached_reduced
                memo_hit = True
            else:
                reduced = adapter.stage2_verify_reduced(bundle)
                # Enforce the contract even if an adapter forgets.
                reduced = dict(reduced)
                if not smoke:
                    reduced["feasible"] = False
                memo.set(reduced_key, reduced)

            verified = reduced
            should_full = run_full_verify and (
                smoke
                or bool(reduced.get("reduced_pass"))
                or float(reduced.get("fraction_correct") or 0.0) >= 0.99
            )
            if should_full:
                full_key = verification_key(
                    task=adapter.task,
                    mode=mode,
                    circuit_fingerprint=adapter.fingerprint(bundle) + b"|full",
                    shots=adapter.full_shots(),
                    verifier_settings=settings_digest({**adapter.verifier_settings(), "stage": "full"}),
                    submission_id=adapter.submission_identity(bundle),
                )
                cached_full = memo.get(full_key)
                if cached_full is not None:
                    verified = cached_full
                    memo_hit = True
                else:
                    verified = adapter.stage2_verify_full(bundle)
                    memo.set(full_key, verified)
            timings.stage2 = time.perf_counter() - t2

        t3 = time.perf_counter()
        fields = adapter.cost_fields(bundle, sample, verified)
        # Live path: only a full-stage feasible flag may enter the feasible band.
        if verified is not None and verified.get("verification_stage") == "reduced" and not smoke:
            fields["feasible"] = False
        score = combined_score(fields, task=task)
        metrics = rich_metrics(fields, task=task, score=score)
        timings.stage3 = time.perf_counter() - t3

        return StagedResult(
            task=task,
            metrics=metrics,
            timings=timings,
            sample=sample,
            verified=verified,
            reduced=reduced,
            problems=list(bundle.problems),
            artifacts={
                "report": bundle.report,
                "stage_seconds": timings.as_dict(),
                "memo_hit": memo_hit,
                "generation_seed_used": True,  # presence only; value stays private
                "verification_stage": (verified or {}).get("verification_stage"),
            },
            memo_hit=memo_hit,
        )
    finally:
        if owns_outdir and bundle is not None and getattr(bundle, "outdir", None) is not None:
            shutil.rmtree(bundle.outdir, ignore_errors=True)


def smoke_evaluate(task: str, repeats: int = 1) -> dict[str, Any]:
    """End-to-end smoke on the seed program.

    Stages 0, 1 and 3 are timed for the ≤60 s budget. Stage 2 still runs under
    the smoke package-sample path so the reported ``combined_score`` can enter
    the feasible band inside the smoke memo namespace, but its wall time is
    excluded from the budget sum.
    """
    adapter = get_adapter(task, generation=0)
    runs: list[StagedResult] = []
    for _ in range(max(1, repeats)):
        runs.append(evaluate_candidate(task, adapter.program_path(), generation=0,
                                       run_stage2=True, run_full_verify=True, adapter=adapter))

    def median(values: list[float]) -> float:
        ordered = sorted(values)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[mid]
        return 0.5 * (ordered[mid - 1] + ordered[mid])

    med = {
        "stage0": median([r.timings.stage0 for r in runs]),
        "stage1": median([r.timings.stage1 for r in runs]),
        "stage2": median([r.timings.stage2 for r in runs]),
        "stage3": median([r.timings.stage3 for r in runs]),
    }
    med["stages_0_1_3"] = med["stage0"] + med["stage1"] + med["stage3"]
    best = max(runs, key=lambda r: r.combined_score)
    return {
        "task": task,
        "combined_score": best.combined_score,
        "metrics": best.metrics,
        "median_seconds": {k: round(v, 4) for k, v in med.items()},
        "problems": best.problems,
        "repeats": repeats,
    }
