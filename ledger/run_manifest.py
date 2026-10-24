"""Run manifest writer and reader (ledger schema v1).

Ported from qrc-thresher `src/qrc_thresher/proof/run_manifest.py` (schema v1.1, Apache-2.0,
https://github.com/clduab11/qrc-thresher). Kept: the dataclass record, `-dirty` commit detection,
atomic temp-file + rename writes and the append-only CSV index. Replaced: the reservoir-computing
fields, with the kickmix submission fields described in `docs/ledger-schema.md`.

A manifest is the proof record for one candidate submission (three tasks) or one Kaggle
submission. A stranger re-checks it by re-hashing the files, re-running the generator at
`generator_commit` and re-running the verifiers named by `verifier_sha256`.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
import os
import platform as _platform
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1"

TASKS = ("invsqrt", "dqi", "dfthcsos")

KINDS = ("candidate", "submission")

# Licence labels a parent can carry (R10). "own" means Praxen-original code, shipped under the
# repository's Apache-2.0 licence. "reference-only" parents (for example the k256.dev dqi
# artifact) may inform work but are never shipped; G5 rejects them.
LICENCES = ("Apache-2.0", "CC-BY-4.0", "own", "reference-only")
SHIPPABLE_LICENCES = frozenset({"Apache-2.0", "CC-BY-4.0", "own"})

GATE_STATUSES = ("PASS", "FAIL", "WAIVED")
GATE_IDS = ("G0", "G1", "G2", "G3", "G4", "G5")
# Gates that must have actually passed (never waived) before a zip is queued or submitted.
UNWAIVABLE_GATES = ("G0", "G3", "G5")

LEDGER_ROOT = Path(__file__).resolve().parent
REPO_ROOT = LEDGER_ROOT.parent
MANIFESTS_DIR = LEDGER_ROOT / "manifests"
INDEX_CSV = MANIFESTS_DIR / "index.csv"

INDEX_FIELDNAMES = [
    "manifest_id",
    "kind",
    "candidate_id",
    "parent_candidate_id",
    "timestamp_utc",
    "operator",
    "generator_commit",
    "salt_label",
    "zip_sha256",
    "invsqrt_ratio",
    "dqi_ratio",
    "dfthcsos_ratio",
    "geometric_mean",
    "last_gate_passed",
    "kaggle_submission_id",
    "submitted_at_utc",
]


class ManifestError(ValueError):
    """A manifest is malformed or violates a ledger rule."""


@dataclass
class Provenance:
    """Where a task's generator came from (R10)."""

    licence: str
    parent_url: str | None = None
    notes: str = ""


@dataclass
class TaskRecord:
    """One task's files, verifier result and provenance.

    Field semantics follow the PRA-171 inventory: `toffoli_count` is the mean number of executed
    Toffoli-like operations per shot (not the static count); `num_qubits` is the verifier's Q
    (largest referenced qubit id + 1 for invsqrt and dqi; persistent + max temporary for dfthcsos).
    `measured` is True only when the numbers come from a captured verifier run.
    """

    task: str
    provenance: Provenance
    files: dict[str, str] = field(default_factory=dict)
    verifier_sha256: str | None = None
    shots: int | None = None
    failures: int | None = None
    eps_plus: float | None = None
    num_qubits: int | None = None
    toffoli_count: float | None = None
    t_count: float | None = None
    rotation_count: float | None = None
    cost: float | None = None
    baseline_cost: float | None = None
    measured: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)

    @property
    def ratio(self) -> float | None:
        return compute_ratio(self.baseline_cost, self.cost)


@dataclass
class GateRecord:
    """The outcome of one gate run, bound to the exact zip it ran on."""

    gate: str
    status: str
    timestamp_utc: str
    zip_sha256: str | None
    reason: str = ""
    evidence_sha256: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunManifest:
    """Ledger schema v1 manifest."""

    manifest_id: str
    kind: str
    candidate_id: str
    timestamp_utc: str
    operator: str
    generator_commit: str
    git_branch: str
    tasks: dict[str, TaskRecord]
    schema_version: str = SCHEMA_VERSION
    parent_candidate_id: str | None = None
    source_candidate_id: str | None = None
    kickmix_build_id: str | None = None
    qualtran_pin: str | None = None
    salt_label: str | None = None
    zip_sha256: str | None = None
    gates: list[GateRecord] = field(default_factory=list)
    kaggle_submission_id: str | None = None
    submitted_at_utc: str | None = None
    python_version: str = ""
    platform: str = ""
    cli_command: str = ""
    notes: str = ""

    @property
    def geometric_mean(self) -> float | None:
        """Competition score: geometric mean of the three task ratios, or None if any is missing."""
        ratios = [self.tasks[t].ratio for t in TASKS if t in self.tasks]
        if len(ratios) != len(TASKS) or any(r is None for r in ratios):
            return None
        return geometric_mean(ratios)  # type: ignore[arg-type]

    def latest_gate(self, gate: str) -> GateRecord | None:
        for record in reversed(self.gates):
            if record.gate == gate:
                return record
        return None

    def gate_cleared(self, gate: str) -> bool:
        """True if the latest record for `gate` is PASS or WAIVED on this manifest's zip."""
        record = self.latest_gate(gate)
        return (
            record is not None
            and record.status in ("PASS", "WAIVED")
            and record.zip_sha256 == self.zip_sha256
        )

    def is_measured(self) -> bool:
        return all(t in self.tasks and self.tasks[t].measured for t in TASKS)

    def last_cleared_gate(self) -> str:
        """The highest gate in G0..G5 order such that it and every earlier gate are cleared."""
        last = ""
        for gate in GATE_IDS:
            if not self.gate_cleared(gate):
                break
            last = gate
        return last

    def shipping_problems(self) -> list[str]:
        """Why this candidate may not be queued or submitted; empty if it may.

        Every gate must be cleared on the current zip, G0/G3/G5 must be real PASS records
        (never waived, even in a hand-edited manifest), and every task must be measured.
        """
        problems = [f"{g} not cleared on the current zip" for g in GATE_IDS
                    if not self.gate_cleared(g)]
        for gate in UNWAIVABLE_GATES:
            record = self.latest_gate(gate)
            if record is not None and record.status != "PASS":
                problems.append(f"{gate} is {record.status}, it must PASS")
        if not self.is_measured():
            problems.append("not every task is measured")
        return problems


# --- Arithmetic -------------------------------------------------------------------------------


def compute_ratio(baseline_cost: float | None, cost: float | None) -> float | None:
    """Per-task score `baseline_cost / cost`, or None if either is unknown or not positive."""
    if baseline_cost is None or cost is None:
        return None
    if not (cost > 0 and baseline_cost > 0) or not math.isfinite(cost):
        return None
    return baseline_cost / cost


def geometric_mean(values: list[float]) -> float:
    if not values or any(v <= 0 for v in values):
        raise ValueError(f"geometric mean needs positive values, got {values}")
    return math.exp(sum(math.log(v) for v in values) / len(values))


# --- Provenance helpers (ported) --------------------------------------------------------------


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Streaming SHA-256 of a file (the 886 MB dqi `.kmb` is hashed without loading it)."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        while chunk := f.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_commit_hash(repo: Path = REPO_ROOT) -> str:
    """Current commit, with `-dirty` appended if the worktree has uncommitted changes."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()
        return f"{commit}-dirty" if status else commit
    except (OSError, subprocess.CalledProcessError) as exc:
        logger.warning("Could not get git commit hash: %s", exc)
        return "unknown"


def git_branch(repo: Path = REPO_ROOT) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        logger.warning("Could not get git branch: %s", exc)
        return "unknown"


def kickmix_build_id(kickmix_so: Path) -> str:
    """Identity of a kickmix binary. The shipped `.so` reports only `__version__ == '0.1'` and its
    source commit is unverified (PRA-171 §2), so its SHA-256 is the build id."""
    return f"sha256:{sha256_file(kickmix_so)}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def operator_id() -> str:
    """The acting agent (Paperclip run env) or the local user."""
    return os.environ.get("PAPERCLIP_AGENT_ID") or os.environ.get("USER") or "unknown"


def _platform_string() -> str:
    try:
        return f"{_platform.system()}-{_platform.release()}-{_platform.machine()}"
    except Exception:  # pragma: no cover - platform lookups do not fail in practice
        return "unknown"


def create_manifest(
    *,
    candidate_id: str,
    tasks: dict[str, TaskRecord],
    kind: str = "candidate",
    parent_candidate_id: str | None = None,
    kickmix_build_id: str | None = None,
    qualtran_pin: str | None = None,
    salt_label: str | None = None,
    zip_sha256: str | None = None,
    repo: Path = REPO_ROOT,
    notes: str = "",
) -> RunManifest:
    """Create a new manifest with run provenance filled in from the environment."""
    info = sys.version_info
    manifest = RunManifest(
        manifest_id=str(uuid4()),
        kind=kind,
        candidate_id=candidate_id,
        timestamp_utc=utc_now(),
        operator=operator_id(),
        generator_commit=git_commit_hash(repo),
        git_branch=git_branch(repo),
        tasks=tasks,
        parent_candidate_id=parent_candidate_id,
        kickmix_build_id=kickmix_build_id,
        qualtran_pin=qualtran_pin,
        salt_label=salt_label,
        zip_sha256=zip_sha256,
        python_version=f"{info.major}.{info.minor}.{info.micro}",
        platform=_platform_string(),
        cli_command=" ".join(sys.argv),
        notes=notes,
    )
    validate(manifest)
    return manifest


# --- Validation -------------------------------------------------------------------------------


def validate(manifest: RunManifest) -> None:
    """Raise ManifestError if the manifest breaks a schema rule."""
    problems: list[str] = []
    if manifest.schema_version != SCHEMA_VERSION:
        problems.append(f"schema_version {manifest.schema_version!r} != {SCHEMA_VERSION!r}")
    if manifest.kind not in KINDS:
        problems.append(f"kind {manifest.kind!r} not in {KINDS}")
    if not manifest.candidate_id:
        problems.append("candidate_id is empty")
    for name, record in manifest.tasks.items():
        if name not in TASKS:
            problems.append(f"unknown task {name!r}")
        if record.task != name:
            problems.append(f"task record {record.task!r} filed under {name!r}")
        if record.provenance.licence not in LICENCES:
            problems.append(f"{name}: licence {record.provenance.licence!r} not in {LICENCES}")
        if record.provenance.licence != "own" and not record.provenance.parent_url:
            problems.append(f"{name}: licence {record.provenance.licence} needs a parent_url")
        for path, digest in record.files.items():
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                problems.append(f"{name}: {path} has a malformed SHA-256")
    for gate in manifest.gates:
        if gate.status not in GATE_STATUSES:
            problems.append(f"gate {gate.gate}: status {gate.status!r} not in {GATE_STATUSES}")
    if manifest.kind == "submission":
        if not manifest.kaggle_submission_id:
            problems.append("a submission manifest needs kaggle_submission_id")
        if not manifest.source_candidate_id:
            problems.append("a submission manifest needs source_candidate_id")
    if problems:
        raise ManifestError("; ".join(problems))


# --- Serialization ----------------------------------------------------------------------------


def to_dict(manifest: RunManifest) -> dict[str, Any]:
    """Plain-JSON form. Derived values (ratios, geometric mean) are written for readers but
    recomputed on load, so a hand-edited ratio cannot drift from cost and baseline."""
    data = asdict(manifest)
    for name, record in manifest.tasks.items():
        data["tasks"][name]["ratio"] = record.ratio
    data["geometric_mean"] = manifest.geometric_mean
    return data


def from_dict(data: dict[str, Any]) -> RunManifest:
    data = dict(data)
    data.pop("geometric_mean", None)
    tasks = {}
    for name, raw in data.pop("tasks").items():
        raw = dict(raw)
        raw.pop("ratio", None)
        raw["provenance"] = Provenance(**raw["provenance"])
        tasks[name] = TaskRecord(**raw)
    gates = [GateRecord(**g) for g in data.pop("gates", [])]
    manifest = RunManifest(tasks=tasks, gates=gates, **data)
    validate(manifest)
    return manifest


def dumps(manifest: RunManifest) -> str:
    return json.dumps(to_dict(manifest), indent=2, sort_keys=True, allow_nan=False,
                      ensure_ascii=False) + "\n"


def loads(text: str) -> RunManifest:
    return from_dict(json.loads(text))


def manifest_path(manifest: RunManifest, root: Path = MANIFESTS_DIR) -> Path:
    if manifest.kind == "submission":
        return root / "submissions" / f"{manifest.candidate_id}.json"
    return root / "candidates" / f"{manifest.candidate_id}.json"


def _atomic_write_text(path: Path, text: str, *, exclusive: bool = False) -> None:
    """Write via a fsynced temporary file (suffix `.tmp`, so it never matches `*.json`), then
    rename. With `exclusive`, refuse to replace an existing file (FileExistsError); the final
    step is a hard link, so two concurrent writers cannot both win."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if exclusive:
            os.link(tmp, path)
            os.unlink(tmp)
        else:
            os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_manifest(manifest: RunManifest, path: Path | None = None, *,
                   exclusive: bool = False) -> Path:
    """Validate and atomically write a manifest; returns the path written. `exclusive` refuses
    to overwrite (new candidates and every submission manifest)."""
    validate(manifest)
    path = path or manifest_path(manifest)
    _atomic_write_text(path, dumps(manifest), exclusive=exclusive)
    logger.info("Manifest written to %s (candidate=%s)", path, manifest.candidate_id)
    return path


def read_manifest(path: Path) -> RunManifest:
    return loads(Path(path).read_text(encoding="utf-8"))


def load_manifests(root: Path = MANIFESTS_DIR) -> list[RunManifest]:
    """Every manifest in `root/candidates/` and `root/submissions/`, oldest first."""
    paths = sorted(Path(root).glob("candidates/*.json")) + sorted(
        Path(root).glob("submissions/*.json")
    )
    manifests = [read_manifest(p) for p in paths if not p.name.startswith(".")]
    return sorted(manifests, key=lambda m: m.timestamp_utc)


def append_to_index(manifest: RunManifest, csv_path: Path = INDEX_CSV) -> None:
    """Append one summary row to the append-only CSV index.

    As in qrc-thresher, this opens in append mode and writes one row; it does not lock across
    processes, so concurrent writers must serialize externally.
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    row = {
        "manifest_id": manifest.manifest_id,
        "kind": manifest.kind,
        "candidate_id": manifest.candidate_id,
        "parent_candidate_id": manifest.parent_candidate_id or "",
        "timestamp_utc": manifest.timestamp_utc,
        "operator": manifest.operator,
        "generator_commit": manifest.generator_commit,
        "salt_label": manifest.salt_label or "",
        "zip_sha256": manifest.zip_sha256 or "",
        "geometric_mean": manifest.geometric_mean,
        "last_gate_passed": manifest.last_cleared_gate(),
        "kaggle_submission_id": manifest.kaggle_submission_id or "",
        "submitted_at_utc": manifest.submitted_at_utc or "",
    }
    for task in TASKS:
        record = manifest.tasks.get(task)
        row[f"{task}_ratio"] = record.ratio if record else None
    with csv_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
