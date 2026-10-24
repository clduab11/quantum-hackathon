"""Evidence collection: verifier logs and file hashes, folded into a manifest.

New for this repository (qrc-thresher has no evidence module); it follows the run_manifest
pattern. An evidence record is a small JSON file under `ledger/evidence/<candidate_id>/` that
lists every log with its SHA-256 and the verifier summaries parsed from those logs. The
manifest's task records point at the evidence by SHA-256, so editing a log after the fact
breaks the chain visibly.

Verifier summaries are the JSON objects the package verifiers print
(`verify_submission_invsqrt.py`, `verify_submission_dqi.py`, `dfthcsos/verify.py`), unchanged.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ledger.run_manifest import (
    LEDGER_ROOT,
    TASKS,
    RunManifest,
    TaskRecord,
    _atomic_write_text,
    operator_id,
    sha256_bytes,
    sha256_file,
    utc_now,
)

EVIDENCE_DIR = LEDGER_ROOT / "evidence"
CIRCUIT_SUFFIXES = (".kmb", ".kmx")


class EvidenceError(ValueError):
    """Evidence is missing, ambiguous or reports a failed verification."""


@dataclass
class LogEntry:
    path: str
    sha256: str
    bytes: int


@dataclass
class EvidenceRecord:
    candidate_id: str
    gate: str
    timestamp_utc: str
    operator: str
    zip_sha256: str | None
    logs: list[LogEntry] = field(default_factory=list)
    summaries: dict[str, Any] = field(default_factory=dict)
    commands: list[str] = field(default_factory=list)
    notes: str = ""


# --- Submission files -------------------------------------------------------------------------


def _visible(path: Path, root: Path) -> bool:
    return "__MACOSX" not in path.relative_to(root).parts


def classify_submission(root: Path) -> dict[str, dict[str, str]]:
    """SHA-256 of every submitted file, grouped by task: `{task: {relpath: sha256}}`.

    This mirrors the metric's discovery (one invsqrt circuit, one dqi circuit, one `dfthcsos`
    directory, searched recursively, `__MACOSX` ignored) only far enough to hash the files.
    G0 is the authority on whether the layout is legal.
    """
    root = Path(root)
    found: dict[str, dict[str, str]] = {}
    for task in ("invsqrt", "dqi"):
        hits = [
            p
            for p in root.rglob(f"{task}.*")
            if p.is_file() and p.suffix in CIRCUIT_SUFFIXES and _visible(p, root)
        ]
        if len(hits) != 1:
            raise EvidenceError(f"expected exactly one {task} circuit, found {len(hits)}")
        found[task] = {hits[0].relative_to(root).as_posix(): sha256_file(hits[0])}
    dirs = [p for p in root.rglob("dfthcsos") if p.is_dir() and _visible(p, root)]
    if len(dirs) != 1:
        raise EvidenceError(f"expected exactly one dfthcsos directory, found {len(dirs)}")
    found["dfthcsos"] = {
        p.relative_to(root).as_posix(): sha256_file(p)
        for p in sorted(dirs[0].rglob("*"))
        if p.is_file() and _visible(p, root)
    }
    if not found["dfthcsos"]:
        raise EvidenceError("dfthcsos directory is empty")
    return found


def hash_log(path: Path, relative_to: Path | None = None) -> LogEntry:
    path = Path(path)
    shown = path.relative_to(relative_to).as_posix() if relative_to else str(path)
    return LogEntry(path=shown, sha256=sha256_file(path), bytes=path.stat().st_size)


def load_summary(path: Path) -> dict[str, Any]:
    """Read one verifier's JSON stdout."""
    return json.loads(Path(path).read_text())


# --- Verifier summary -> task record ----------------------------------------------------------


def apply_verifier_summary(
    record: TaskRecord,
    summary: dict[str, Any],
    *,
    verifier_sha256: str | None = None,
    baseline_cost: float | None = None,
) -> TaskRecord:
    """Copy one verifier summary into a task record and mark it measured.

    Raises EvidenceError if the verifier did not pass: an unverified task is never recorded as
    measured (AGENTS.md, Verification).
    """
    if summary.get("status") != "PASS":
        raise EvidenceError(f"{record.task}: verifier status {summary.get('status')!r}: "
                            f"{summary.get('error', 'no error text')}")
    record.cost = float(summary["score"])
    record.num_qubits = int(summary["num_qubits"])
    record.toffoli_count = float(summary["toffoli_count"])
    record.shots = int(summary["verified_shots"])
    if record.task == "invsqrt":
        # The verifier raises on any out-of-tolerance shot, so a PASS means zero failures.
        record.failures = 0
        record.t_count = float(summary["t_count"])
        record.rotation_count = float(summary["rotation_count"])
        keys = ("toffoli_equivalent", "max_toffoli_count", "rotation_eps",
                "worst_error_over_tolerance", "worst_x", "circuit_sha256")
    elif record.task == "dqi":
        record.failures = int(summary["value_errors"]) + int(summary["phase_errors"])
        record.eps_plus = float(summary["effective_error_rate"])
        keys = ("value_errors", "phase_errors", "empirical_error_rate", "repetition_factor",
                "log2_delta", "max_toffoli_count", "mean_error_weight", "circuit_sha256")
    elif record.task == "dfthcsos":
        keys = ("lambda_eff", "brot", "batch_size", "num_circuits", "submission_sha256")
        for name in ("Lambda", "E_gap", "error_1", "error_2"):
            if name in summary.get("metrics", {}):
                record.metrics[name] = summary["metrics"][name]
        resources = summary.get("resources", {})
        for name in ("angles_qubits", "persistent_qubits", "temporary_qubits"):
            if name in resources:
                record.metrics[name] = resources[name]
    else:
        raise EvidenceError(f"unknown task {record.task!r}")
    for key in keys:
        if key in summary:
            record.metrics[key] = summary[key]
    if verifier_sha256 is not None:
        record.verifier_sha256 = verifier_sha256
    if baseline_cost is not None:
        record.baseline_cost = float(baseline_cost)
    record.measured = True
    return record


# --- Evidence records -------------------------------------------------------------------------


def evidence_path(candidate_id: str, gate: str, root: Path = EVIDENCE_DIR) -> Path:
    return Path(root) / candidate_id / f"{gate}.json"


def write_evidence(record: EvidenceRecord, root: Path = EVIDENCE_DIR) -> tuple[Path, str]:
    """Write an evidence record; returns its path and the SHA-256 of the bytes written."""
    text = json.dumps(asdict(record), indent=2, sort_keys=True, allow_nan=False) + "\n"
    path = evidence_path(record.candidate_id, record.gate, root)
    _atomic_write_text(path, text)
    return path, sha256_bytes(text.encode())


def collect_verifier_evidence(
    manifest: RunManifest,
    gate: str,
    summaries: dict[str, dict[str, Any]],
    *,
    logs: Sequence[Path] = (),
    log_root: Path | None = None,
    verifier_hashes: dict[str, str] | None = None,
    baseline_costs: dict[str, float] | None = None,
    commands: Sequence[str] = (),
    notes: str = "",
    root: Path = EVIDENCE_DIR,
) -> str:
    """Fold verifier summaries into `manifest` and write the evidence record.

    Every summary must be a PASS. Returns the evidence SHA-256, which is also appended to each
    updated task record's `evidence` list.
    """
    verifier_hashes = verifier_hashes or {}
    baseline_costs = baseline_costs or {}
    unknown = set(summaries) - set(TASKS)
    if unknown:
        raise EvidenceError(f"summaries for unknown tasks: {sorted(unknown)}")
    # All or nothing: fill copies, write the evidence, and only then swap the copies in, so a
    # failure part-way never leaves a task marked measured.
    updated: dict[str, TaskRecord] = {}
    for task, summary in summaries.items():
        if task not in manifest.tasks:
            raise EvidenceError(f"manifest has no task record for {task}")
        updated[task] = apply_verifier_summary(
            copy.deepcopy(manifest.tasks[task]),
            summary,
            verifier_sha256=verifier_hashes.get(task),
            baseline_cost=baseline_costs.get(task),
        )
    record = EvidenceRecord(
        candidate_id=manifest.candidate_id,
        gate=gate,
        timestamp_utc=utc_now(),
        operator=operator_id(),
        zip_sha256=manifest.zip_sha256,
        logs=[hash_log(p, log_root) for p in logs],
        summaries=summaries,
        commands=list(commands),
        notes=notes,
    )
    _, digest = write_evidence(record, root)
    for task, task_record in updated.items():
        task_record.evidence.append(digest)
        manifest.tasks[task] = task_record
    return digest
