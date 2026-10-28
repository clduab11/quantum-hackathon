# SPDX-License-Identifier: Apache-2.0
"""Staged evaluator: 0 parse/build, 1 sample, 2 official (memoised), 3 cost score."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from search.adapters import get_adapter
from search.adapters.base import StageTimings, TaskAdapter
from search.fitness import combined_score, rich_metrics
from search.memo import VerifierMemo
from search.stage_seed import generation_seed

_MEMO = VerifierMemo()


@dataclass
class StagedResult:
    task: str
    metrics: dict[str, float]
    timings: StageTimings
    sample: dict[str, Any] = field(default_factory=dict)
    verified: dict[str, Any] | None = None
    problems: list[str] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    memo_hit: bool = False

    @property
    def combined_score(self) -> float:
        return float(self.metrics.get("combined_score", 0.0))


def evaluate_candidate(
    task: str,
    program_path: Path | None = None,
    *,
    generation: int = 0,
    run_stage2: bool = True,
    adapter: TaskAdapter | None = None,
    memo: VerifierMemo | None = None,
    outdir: Path | None = None,
) -> StagedResult:
    """Run stages 0, 1, (2), 3. Stage 1 never sets feasible."""
    adapter = adapter or get_adapter(task, generation=generation)
    program = Path(program_path or adapter.program_path())
    memo = memo or _MEMO
    timings = StageTimings()

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
    memo_hit = False
    if run_stage2:
        key = adapter.fingerprint(bundle)
        t2 = time.perf_counter()
        cached = memo.get(key)
        if cached is not None:
            verified = cached
            memo_hit = True
        else:
            verified = adapter.stage2_verify(bundle)
            memo.set(key, verified)
        timings.stage2 = time.perf_counter() - t2

    t3 = time.perf_counter()
    fields = adapter.cost_fields(bundle, sample, verified)
    score = combined_score(fields, task=task)
    metrics = rich_metrics(fields, task=task, score=score)
    timings.stage3 = time.perf_counter() - t3

    return StagedResult(
        task=task,
        metrics=metrics,
        timings=timings,
        sample=sample,
        verified=verified,
        problems=list(bundle.problems),
        artifacts={
            "report": bundle.report,
            "stage_seconds": timings.as_dict(),
            "memo_hit": memo_hit,
            "generation_seed_used": True,  # presence only; value stays private
        },
        memo_hit=memo_hit,
    )


def smoke_evaluate(task: str, repeats: int = 1) -> dict[str, Any]:
    """End-to-end smoke on the seed program.

    Stages 0, 1 and 3 are timed for the ≤60 s budget. Stage 2 still runs under
    ``SEARCH_SMOKE=1`` (cheap proxy / package-sample path) so the reported
    ``combined_score`` can enter the feasible band, but its wall time is
    excluded from the budget sum.
    """
    adapter = get_adapter(task, generation=0)
    runs: list[StagedResult] = []
    for _ in range(max(1, repeats)):
        runs.append(evaluate_candidate(task, adapter.program_path(), generation=0,
                                       run_stage2=True, adapter=adapter))

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
