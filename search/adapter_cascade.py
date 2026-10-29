# SPDX-License-Identifier: Apache-2.0
"""OpenEvolve cascade stages for invsqrt and dqi via task adapters.

Mirrors the dfthcsos ``evaluator.py`` cascade contract:

* stage 1 — build + sample (never feasible)
* stage 2 — reduced / proxy verify (never feasible; score below 0.5)
* stage 3 — full official verify (sole feasibility arbiter)

``SEARCH_TASK`` selects the adapter. Compatible with OpenEvolve's
``evaluate_stage1`` / ``evaluate_stage2`` / ``evaluate_stage3`` entry points.
"""
from __future__ import annotations

import os
import shutil
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from search.adapters import get_adapter
from search.adapters.base import CandidateBundle, TaskAdapter
from search.evaluator import STAGE1_THRESHOLD, STAGE2_THRESHOLD
from search.fitness import combined_score, log_safe, rich_metrics
from search.memo import VerifierMemo, settings_digest, verification_key
from search.stage_seed import generation_seed

try:
    from openevolve.evaluation_result import EvaluationResult
except ImportError:  # pragma: no cover
    @dataclass
    class EvaluationResult:  # type: ignore[no-redef]
        metrics: dict
        artifacts: dict = field(default_factory=dict)


_MEMO = VerifierMemo()
_STATE: dict[str, dict[str, Any]] = {}


def _task_name(task: str | None = None) -> str:
    """Resolve the active search task from argument or ``SEARCH_TASK``."""
    return task or os.environ.get("SEARCH_TASK", "invsqrt")


def _adapter_for(task: str, generation: int = 0) -> TaskAdapter:
    """Construct the task adapter for ``task``."""
    return get_adapter(task, generation=generation)


def _state_key(program_path: str, task: str) -> str:
    """Per-program / per-task cache key for cascade state between stages."""
    return f"{task}:{program_path}"


def _cleanup(program_path: str, task: str) -> None:
    """Remove cascade state and delete the owned stage0 build directory."""
    state = _STATE.pop(_state_key(str(program_path), task), None)
    if state is None:
        return
    bundle = state.get("bundle")
    outdir = getattr(bundle, "outdir", None) if bundle is not None else None
    if outdir is not None:
        shutil.rmtree(outdir, ignore_errors=True)


def _failed_result(program_path: str, task: str, stage: int, exc: BaseException) -> EvaluationResult:
    """Return a zero score after an evaluator exception; never re-raise."""
    _cleanup(program_path, task)
    detail = str(exc)
    if len(detail) > 300:
        detail = detail[:300]
    metrics = {
        "combined_score": 0.0,
        "ratio": 0.0,
        "predicted_ratio": 0.0,
        "q": 0.0,
        "t": 0.0,
        "q_bin": 0.0,
        "t_bin": 0.0,
        "stage1_passed": 0.0,
        "stage2_passed": 0.0,
        "stage3_passed": 0.0,
        "stage_reached": float(stage),
        "feasible": 0.0,
        "fraction_correct": 0.0,
        "max_error_over_tol": 9.0,
        "ancilla_dirty_fraction": 0.0,
        "phase_wrong_fraction": 0.0,
        "toffoli_count": 0.0,
        "qubit_count": 0.0,
    }
    return EvaluationResult(
        metrics=metrics,
        artifacts={
            "summary": (
                f"task={task} stage {stage}: {type(exc).__name__}: {detail}"
            ),
            "evaluator_traceback": traceback.format_exc()[-3000:],
        },
    )


def _score_fields(task: str, sample: dict[str, Any], verified: dict[str, Any] | None,
                  adapter: TaskAdapter, bundle: CandidateBundle) -> dict[str, Any]:
    """Build cost fields; force infeasible when only a reduced result is present."""
    fields = adapter.cost_fields(bundle, sample, verified)
    if verified is not None and verified.get("verification_stage") == "reduced":
        fields["feasible"] = False
    fields["task"] = task
    return fields


def _to_result(task: str, fields: dict[str, Any], *, stage_reached: int,
               problems: list[str], artifacts: dict[str, Any] | None = None) -> EvaluationResult:
    """Wrap Deb-layered fields as an OpenEvolve ``EvaluationResult``."""
    score = combined_score(fields, task=task)
    metrics = rich_metrics(fields, task=task, score=score)
    metrics["stage_reached"] = float(stage_reached)
    metrics["stage1_passed"] = 1.0 if stage_reached >= 1 and not problems else 0.0
    metrics["stage2_passed"] = 1.0 if stage_reached >= 2 and fields.get("fraction_correct", 0) >= 0.99 else 0.0
    metrics["stage3_passed"] = 1.0 if fields.get("feasible") else 0.0
    metrics["q"] = metrics.get("qubit_count", 0.0)
    metrics["t"] = metrics.get("toffoli_count", 0.0)
    metrics["q_bin"] = metrics["q"]
    metrics["t_bin"] = metrics["t"]
    if problems and score >= STAGE1_THRESHOLD:
        metrics["combined_score"] = min(score, STAGE1_THRESHOLD - 1e-6)
    art = {"summary": f"task={task} stage={stage_reached} score={metrics['combined_score']:.6f}"}
    if problems:
        art["summary"] += "; problems: " + "; ".join(problems)
    if artifacts:
        art.update({k: str(v)[:4000] for k, v in artifacts.items()})
    return EvaluationResult(metrics=metrics, artifacts=art)


def evaluate_stage1(program_path: str, task: str | None = None) -> EvaluationResult:
    """Build the candidate and run the stage-1 sample; never marks feasible."""
    task = _task_name(task)
    try:
        adapter = _adapter_for(task)
        program = Path(program_path)
        bundle = adapter.stage0_build(program)
        sample = {"feasible": False, "fraction_correct": 0.0, "max_error_over_tol": 9.0,
                  "ancilla_dirty_fraction": 1.0, "phase_wrong_fraction": 1.0,
                  "toffoli_count": 1.0, "qubit_count": 1.0}
        if not bundle.problems:
            sample = adapter.stage1_sample(bundle, generation_seed(0))
            sample["feasible"] = False
        fields = _score_fields(task, sample, None, adapter, bundle)
        state = {
            "bundle": bundle,
            "sample": sample,
            "reduced": None,
            "verified": None,
            "adapter_task": task,
        }
        _STATE[_state_key(str(program), task)] = state
        result = _to_result(task, fields, stage_reached=1, problems=list(bundle.problems),
                            artifacts={"report": bundle.report})
        if result.metrics["combined_score"] < STAGE1_THRESHOLD:
            _cleanup(str(program), task)
        return result
    except Exception as exc:  # noqa: BLE001
        return _failed_result(program_path, task, 1, exc)


def evaluate_stage2(program_path: str, task: str | None = None) -> EvaluationResult:
    """Reduced / proxy verify. Never marks feasible; must clear ``STAGE2_THRESHOLD``."""
    task = _task_name(task)
    try:
        key = _state_key(str(program_path), task)
        state = _STATE.get(key)
        if state is None:
            evaluate_stage1(program_path, task=task)
            state = _STATE.get(key)
            if state is None:
                # Stage 1 failed and cleaned up; re-run would loop. Return zero.
                return _to_result(
                    task,
                    {"task": task, "feasible": False, "fraction_correct": 0.0,
                     "max_error_over_tol": 9.0, "ancilla_dirty_fraction": 0.0,
                     "phase_wrong_fraction": 0.0, "toffoli_count": 1.0, "qubit_count": 1.0},
                    stage_reached=1,
                    problems=["stage1 did not retain state"],
                )
        adapter = _adapter_for(task)
        bundle: CandidateBundle = state["bundle"]
        sample = state["sample"]
        if bundle.problems:
            fields = _score_fields(task, sample, None, adapter, bundle)
            result = _to_result(task, fields, stage_reached=1, problems=list(bundle.problems))
            _cleanup(program_path, task)
            return result

        mode = "smoke" if (bundle.report or {}).get("smoke_package_sample") else "full"
        memo_key = verification_key(
            task=task,
            mode=mode,
            circuit_fingerprint=adapter.fingerprint(bundle) + b"|reduced",
            shots=adapter.reduced_shots(),
            verifier_settings=settings_digest({**adapter.verifier_settings(), "stage": "reduced"}),
            submission_id=adapter.submission_identity(bundle),
        )
        cached = _MEMO.get(memo_key)
        if cached is not None:
            reduced = cached
        else:
            reduced = adapter.stage2_verify_reduced(bundle)
            reduced = dict(reduced)
            reduced["feasible"] = False
            _MEMO.set(memo_key, reduced)
        state["reduced"] = reduced
        fields = _score_fields(task, sample, reduced, adapter, bundle)
        result = _to_result(task, fields, stage_reached=2, problems=[],
                            artifacts={"reduced": reduced})
        if result.metrics["combined_score"] < STAGE2_THRESHOLD:
            _cleanup(program_path, task)
        return result
    except Exception as exc:  # noqa: BLE001
        return _failed_result(program_path, task, 2, exc)


def evaluate_stage3(program_path: str, task: str | None = None) -> EvaluationResult:
    """Full official verify; sole stage that may mark the candidate feasible."""
    task = _task_name(task)
    try:
        key = _state_key(str(program_path), task)
        state = _STATE.get(key)
        if state is None or state.get("reduced") is None:
            evaluate_stage2(program_path, task=task)
            state = _STATE.get(key)
            if state is None:
                return _to_result(
                    task,
                    {"task": task, "feasible": False, "fraction_correct": 0.0,
                     "max_error_over_tol": 9.0, "ancilla_dirty_fraction": 0.0,
                     "phase_wrong_fraction": 0.0, "toffoli_count": 1.0, "qubit_count": 1.0},
                    stage_reached=2,
                    problems=["stage2 did not retain state"],
                )
        adapter = _adapter_for(task)
        bundle: CandidateBundle = state["bundle"]
        sample = state["sample"]
        if bundle.problems:
            fields = _score_fields(task, sample, None, adapter, bundle)
            result = _to_result(task, fields, stage_reached=1, problems=list(bundle.problems))
            _cleanup(program_path, task)
            return result

        mode = "smoke" if (bundle.report or {}).get("smoke_package_sample") else "full"
        memo_key = verification_key(
            task=task,
            mode=mode,
            circuit_fingerprint=adapter.fingerprint(bundle) + b"|full",
            shots=adapter.full_shots(),
            verifier_settings=settings_digest({**adapter.verifier_settings(), "stage": "full"}),
            submission_id=adapter.submission_identity(bundle),
        )
        cached = _MEMO.get(memo_key)
        if cached is not None:
            verified = cached
        else:
            verified = adapter.stage2_verify_full(bundle)
            _MEMO.set(memo_key, verified)
        state["verified"] = verified
        fields = _score_fields(task, sample, verified, adapter, bundle)
        result = _to_result(task, fields, stage_reached=3, problems=[],
                            artifacts={"verified": verified})
        _cleanup(program_path, task)
        return result
    except Exception as exc:  # noqa: BLE001
        return _failed_result(program_path, task, 3, exc)


def evaluate(program_path: str, task: str | None = None) -> EvaluationResult:
    """Non-cascade entry: stages 1→2→3 with the same thresholds as dfthcsos."""
    result = evaluate_stage1(program_path, task=task)
    if result.metrics["combined_score"] < STAGE1_THRESHOLD:
        return result
    result = evaluate_stage2(program_path, task=task)
    if result.metrics["combined_score"] < STAGE2_THRESHOLD:
        return result
    return evaluate_stage3(program_path, task=task)


# Re-export log_safe so tests can assert MAP-Elites features without importing fitness.
__all__ = [
    "EvaluationResult",
    "evaluate",
    "evaluate_stage1",
    "evaluate_stage2",
    "evaluate_stage3",
    "log_safe",
]
