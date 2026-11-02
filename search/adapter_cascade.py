# SPDX-License-Identifier: Apache-2.0
"""OpenEvolve cascade stages for invsqrt and dqi via task adapters.

Mirrors the dfthcsos ``evaluator.py`` cascade contract:

* stage 1 — build + sample (never feasible)
* stage 2 — reduced / proxy verify (never feasible; score below 0.5)
* stage 3 — full official verify (sole feasibility arbiter)

``SEARCH_TASK`` selects the adapter. Compatible with OpenEvolve's
``evaluate_stage1`` / ``evaluate_stage2`` / ``evaluate_stage3`` entry points.

Stage 0 (the adapter's AST parse) runs inside ``stage0_build`` before any subprocess. Verifier results
and whole-program results share the persistent memo of search/memo.py (``$SEARCH_RUN_DIR/verifier_memo.jsonl``):
an identical program source is answered without a build, and stage 3 refuses to run the full verifier
unless the reduced stage of the same candidate passed.
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
from search.memo import (
    VerifierMemo, code_fingerprint, program_key, program_sha256, settings_digest, verification_key,
)
from search.stage_seed import generation_seed

try:
    from openevolve.evaluation_result import EvaluationResult
except ImportError:  # pragma: no cover
    @dataclass
    class EvaluationResult:  # type: ignore[no-redef]
        metrics: dict
        artifacts: dict = field(default_factory=dict)


_MEMO = VerifierMemo()  # persisted under $SEARCH_RUN_DIR (or $SEARCH_MEMO_PATH); in-process without either
_STATE: dict[str, dict[str, Any]] = {}
_CASCADE_FINGERPRINT: str | None = None


def _program_mode() -> str:
    return "smoke" if os.environ.get("SEARCH_SMOKE") == "1" else "full"


# The verifier, proxy and sample code the adapters call; a change to any of it misses the program memo.
VERIFIER_MODULES = ("tasks.invsqrt.gates", "tasks.invsqrt.signed_digit", "tasks.dqi.algebra", "tasks.dfthcsos.gates",
                    "dqi.verify_submission_dqi", "dfthcsos.verify", "dfthcsos.scoreinfra.circuits", "kickmix")


def _cascade_fingerprint() -> str:
    """Short digest of the cascade, scoring, adapter, verifier and proxy code bound into program-memo keys."""
    global _CASCADE_FINGERPRINT
    if _CASCADE_FINGERPRINT is None:
        here = Path(__file__).resolve().parent
        _CASCADE_FINGERPRINT = code_fingerprint(
            files=[here / "adapter_cascade.py", here / "fitness.py", *sorted((here / "adapters").glob("*.py"))],
            modules=VERIFIER_MODULES)
    return _CASCADE_FINGERPRINT


def _program_memo_key(program_path: str, task: str, adapter: TaskAdapter) -> bytes | None:
    """Memo key for the whole evaluation of one program source under ``adapter``; ``None`` when unbindable."""
    digest = program_sha256(program_path)
    if digest is None:
        return None
    try:
        settings = settings_digest({
            **dict(adapter.verifier_settings() or {}),
            "reduced_shots": adapter.reduced_shots(), "full_shots": adapter.full_shots(),
            "cascade": _cascade_fingerprint(),
        })
        return program_key(task=task, mode=_program_mode(), program_sha256=digest, settings=settings)
    except Exception:  # noqa: BLE001 - an adapter that cannot describe its settings gets no program memo
        return None


def _cached_program_result(program_path: str, task: str, adapter: TaskAdapter) -> EvaluationResult | None:
    """The recorded result of an identical program source, if the memo holds one: no build, no verifier."""
    if _state_key(str(program_path), task) in _STATE:  # this path is mid-cascade; finish that
        return None
    key = _program_memo_key(program_path, task, adapter)
    if key is None:
        return None
    cached = _MEMO.get(key)
    if not isinstance(cached, dict) or not isinstance(cached.get("metrics"), dict):
        return None
    artifacts = {str(k): str(v) for k, v in (cached.get("artifacts") or {}).items()}
    artifacts["memo_hit"] = (f"program source sha256 {str(cached.get('program_sha256') or '')[:12]} was evaluated "
                             f"before (final stage {cached.get('final_stage')}); its result is reused without a build")
    return EvaluationResult(metrics=dict(cached["metrics"]), artifacts=artifacts)


def _remember(program_path: str, task: str, adapter: TaskAdapter, result: EvaluationResult, final_stage: int) -> None:
    """Store a terminal cascade result under the program-source key (negative unless stage 3 passed)."""
    key = _program_memo_key(program_path, task, adapter)
    if key is None:
        return
    _MEMO.set(key, {
        "metrics": dict(result.metrics), "artifacts": dict(result.artifacts), "final_stage": int(final_stage),
        "program_sha256": program_sha256(program_path), "task": task,
    }, negative=not result.metrics.get("stage3_passed"))


def _reduced_passed(reduced: dict[str, Any] | None) -> bool:
    """The reduced stage counts as passed on ``reduced_pass`` or a fraction_correct of at least 0.99 (staged.py's rule)."""
    if not reduced:
        return False
    return bool(reduced.get("reduced_pass")) or float(reduced.get("fraction_correct") or 0.0) >= 0.99


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
        cached = _cached_program_result(program_path, task, adapter)
        if cached is not None:
            return cached
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
            _remember(program_path, task, adapter, result, final_stage=1)
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
            cached = _cached_program_result(program_path, task, _adapter_for(task))
            if cached is not None:
                return cached
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
            _remember(program_path, task, adapter, result, final_stage=1)
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
            _remember(program_path, task, adapter, result, final_stage=2)
        return result
    except Exception as exc:  # noqa: BLE001
        return _failed_result(program_path, task, 2, exc)


def evaluate_stage3(program_path: str, task: str | None = None) -> EvaluationResult:
    """Full official verify; sole stage that may mark the candidate feasible."""
    task = _task_name(task)
    try:
        key = _state_key(str(program_path), task)
        state = _STATE.get(key)
        if state is None:
            cached = _cached_program_result(program_path, task, _adapter_for(task))
            if cached is not None:
                return cached
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
            _remember(program_path, task, adapter, result, final_stage=1)
            return result

        reduced = state.get("reduced")
        if not _reduced_passed(reduced):  # the full verifier is reached only through a reduced PASS
            fields = _score_fields(task, sample, reduced, adapter, bundle)
            result = _to_result(task, fields, stage_reached=2 if reduced else 1, problems=[], artifacts={
                "reduced": reduced,
                "gated": "full verification needs a reduced-stage PASS first; the reduced stage did not pass",
            })
            _cleanup(program_path, task)
            _remember(program_path, task, adapter, result, final_stage=2)
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
        _remember(program_path, task, adapter, result, final_stage=3)
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
