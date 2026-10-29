# SPDX-License-Identifier: Apache-2.0
"""Deb-layered dense fitness for the three VQCC tasks (research report §6.2).

Infeasible candidates live in ``[0, 0.5)`` and can never outrank a feasible one.
Feasible candidates live in ``[0.5, 1]`` and compare on a log-cost linear map.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

# Default log-cost window: wide enough for every task's reference and for
# aggressive compression (about 0.01× to 100× the reference product).
LOG_COST_MIN = 5.0
LOG_COST_MAX = 40.0

TASK_LOG_COST = {
    "invsqrt": ("log_qubits", "log_cost_c"),          # log Q + log C
    "dqi": ("log_r_eps", "log_qubits", "log_qubits", "log_toffoli"),  # log R + 2 log Q + log T
    "dfthcsos": ("log_lambda_eff", "log_toffoli", "log_qubits"),
}


def clip(value: float, low: float, high: float) -> float:
    """Clamp ``value`` into ``[low, high]``."""
    return low if value < low else high if value > high else value


def _finite(value: Any, default: float = 0.0) -> float:
    """Coerce ``value`` to a finite float, else ``default``."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def log_safe(value: Any, floor: float = 1e-12) -> float:
    """Natural log of ``value``, floored so missing/zero inputs stay defined."""
    return math.log(max(_finite(value, floor), floor))


def graded_violation(res: Mapping[str, Any]) -> float:
    """Max of the four graded infeasibility terms (research report §6.2)."""
    fraction_correct = clip(_finite(res.get("fraction_correct"), 0.0), 0.0, 1.0)
    max_error = _finite(res.get("max_error_over_tol"), 0.0)
    ancilla = clip(_finite(res.get("ancilla_dirty_fraction"), 0.0), 0.0, 1.0)
    phase = clip(_finite(res.get("phase_wrong_fraction"), 0.0), 0.0, 1.0)
    return max(
        1.0 - fraction_correct,
        clip(max_error - 1.0, 0.0, 9.0),
        ancilla,
        phase,
    )


def log_cost_terms(task: str, res: Mapping[str, Any]) -> dict[str, float]:
    """Fill the log-cost ingredients the task needs; missing keys default safely.

    ``lambda_eff`` is floored at 1.0 after the finite-value fallback so a missing,
    zero, or invalid value cannot improve the feasible score.
    """
    toffoli = max(_finite(res.get("toffoli_count"), 0.0), 1.0)
    qubits = max(_finite(res.get("qubit_count", res.get("num_qubits")), 0.0), 1.0)
    lambda_eff = max(_finite(res.get("lambda_eff"), 1.0), 1.0)
    out = {
        "log_toffoli": log_safe(toffoli),
        "log_qubits": log_safe(qubits),
        "log_cost_c": log_safe(res.get("cost_c", toffoli)),
        "log_lambda_eff": log_safe(lambda_eff),
        "log_r_eps": log_safe(res.get("r_eps", res.get("R_eps", 1.0))),
    }
    # Allow callers to override any term explicitly.
    for key in ("log_toffoli", "log_qubits", "log_cost_c", "log_lambda_eff", "log_r_eps"):
        if key in res and res[key] is not None:
            out[key] = _finite(res[key], out[key])
    if task not in TASK_LOG_COST:
        raise ValueError(f"unknown task {task!r}; expected one of {sorted(TASK_LOG_COST)}")
    return out


def task_log_cost(task: str, res: Mapping[str, Any]) -> float:
    """Sum the task's log-cost terms from ``log_cost_terms``."""
    terms = log_cost_terms(task, res)
    return sum(terms[name] for name in TASK_LOG_COST[task])


def feasible_score(log_cost: float, *, log_min: float = LOG_COST_MIN, log_max: float = LOG_COST_MAX) -> float:
    """Map log cost into ``[0.5, 1]``; lower cost → higher score."""
    if log_max <= log_min:
        raise ValueError("log_max must exceed log_min")
    normalised = clip((log_max - log_cost) / (log_max - log_min), 0.0, 1.0)
    return 0.5 + 0.5 * normalised


def combined_score(res: Mapping[str, Any], *, task: str | None = None,
                   log_min: float = LOG_COST_MIN, log_max: float = LOG_COST_MAX) -> float:
    """Deb-layered scalar used as OpenEvolve's ``combined_score``.

    ``res["feasible"]`` is the only gate into the feasible band. Stage-1 sample
    metrics may populate the violation terms, but they must not set feasible.
    """
    if not res.get("feasible"):
        # Strictly below the feasible floor even when every graded term is zero
        # (stage 1 must never be the final feasibility arbiter).
        violation = graded_violation(res)
        return min(0.5 * (1.0 / (1.0 + violation)), 0.5 - 1e-12)

    resolved_task = task or str(res.get("task") or "")
    if not resolved_task:
        raise ValueError("combined_score needs task=... or res['task']")
    if "log_cost" in res and res["log_cost"] is not None:
        cost = _finite(res["log_cost"])
    else:
        cost = task_log_cost(resolved_task, res)
    return feasible_score(cost, log_min=log_min, log_max=log_max)


def rich_metrics(res: Mapping[str, Any], *, task: str, score: float | None = None) -> dict[str, float]:
    """Always-returned metric dictionary (selection uses ``combined_score`` only)."""
    toffoli = _finite(res.get("toffoli_count"), 0.0)
    qubits = _finite(res.get("qubit_count", res.get("num_qubits")), 0.0)
    metrics: dict[str, float] = {
        "combined_score": _finite(score if score is not None else combined_score(res, task=task)),
        "toffoli_count": toffoli,
        "qubit_count": qubits,
        "log_toffoli": log_safe(max(toffoli, 1.0)),
        "log_qubits": log_safe(max(qubits, 1.0)),
        "fraction_correct": _finite(res.get("fraction_correct"), 0.0),
        "max_error_over_tol": _finite(res.get("max_error_over_tol"), 0.0),
        "feasible": 1.0 if res.get("feasible") else 0.0,
    }
    # Task-specific rich fields (present even when zero / unknown).
    metrics["margin_min"] = _finite(res.get("margin_min"), 0.0)
    metrics["k_failures"] = _finite(res.get("k_failures"), 0.0)
    metrics["eps_plus"] = _finite(res.get("eps_plus"), 0.0)
    metrics["error_1"] = _finite(res.get("error_1", res.get("error1")), 0.0)
    metrics["error_2"] = _finite(res.get("error_2", res.get("error2")), 0.0)
    metrics["lambda_eff"] = _finite(res.get("lambda_eff"), 0.0)
    metrics["E_gap"] = _finite(res.get("E_gap", res.get("e_gap")), 0.0)
    return metrics
