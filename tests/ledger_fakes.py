"""Stand-in gate hooks for the ledger tests. Each records its call in CALLS; BEHAVIOUR sets what
it returns ("PASS", "FAIL: ...", or an exception instance to raise)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

CALLS: list[str] = []
BEHAVIOUR: dict[str, Any] = {}

SHOTS = {"invsqrt": 200540928, "dqi": 102400, "dfthcsos": 254464}
BASELINES = {"invsqrt": 2076774.233715282, "dqi": 24440968846372.203,
             "dfthcsos": 3355599588.3155365}


def reset() -> None:
    CALLS.clear()
    BEHAVIOUR.clear()


def _status(name: str) -> dict[str, Any]:
    CALLS.append(name)
    behaviour = BEHAVIOUR.get(name, "PASS")
    if isinstance(behaviour, Exception):
        raise behaviour
    return {"status": behaviour}


def g0(submission_dir: Path) -> object:
    _status("g0")
    return object()  # like P0-4's preflight: parsed circuits on success, raises on rejection


def g1(submission_dir: Path) -> dict[str, Any]:
    return _status("g1")


def g2(submission_dir: Path) -> dict[str, Any]:
    return _status("g2")


def summaries(divisor: float = 2.0) -> dict[str, dict[str, Any]]:
    """Verifier summaries whose costs are `baseline / divisor`, so every ratio is `divisor`."""
    common = {"status": "PASS", "num_qubits": 100, "toffoli_count": 1000.0}
    return {
        "invsqrt": {**common, "score": BASELINES["invsqrt"] / divisor, "t_count": 1.0,
                    "rotation_count": 37.0, "verified_shots": SHOTS["invsqrt"]},
        "dqi": {**common, "score": BASELINES["dqi"] / divisor, "value_errors": 1,
                "phase_errors": 0, "effective_error_rate": 0.0017,
                "verified_shots": SHOTS["dqi"]},
        "dfthcsos": {**common, "score": BASELINES["dfthcsos"] / divisor, "lambda_eff": 49.3,
                     "metrics": {"Lambda": 308.4, "E_gap": 3.97}, "verified_shots": SHOTS["dfthcsos"]},
    }


def g3(submission_dir: Path, *, salt_label: str | None, shot_divisor: int = 1) -> dict[str, Any]:
    CALLS.append("g3")
    if "g3" in BEHAVIOUR:
        behaviour = BEHAVIOUR["g3"]
        if isinstance(behaviour, Exception):
            raise behaviour
        return behaviour
    return {
        "status": "PASS",
        "kickmix_build_id": "sha256:" + "c" * 64,
        "verifier_hashes": {t: "a" * 64 for t in SHOTS},
        "baseline_costs": BASELINES,
        "tasks": summaries(BEHAVIOUR.get("g3_divisor", 2.0)),
    }
