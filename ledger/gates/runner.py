"""Gate runner: G0–G5, in order, config-driven from `configs/gates/*.yaml`.

New for this repository (qrc-thresher has no gate runner); it follows the run_manifest pattern.

Rules the runner enforces:

- Gates run in the configured order G0, G1, G2, G3, G4, G5. A gate runs only if every earlier gate
  is cleared (PASS, or WAIVED where the config allows it) **on the same zip SHA-256**. So a
  candidate cannot reach G3 without G2 passing, and a zip changed after G2 has to start again.
- Only gates marked `waivable: true` can be waived, and a waiver needs a written reason. The
  waiver is stored in the manifest like any other gate result.
- A check that raises, or a hook that is not installed, is a FAIL, never a skip.
- Only a candidate that meets the shipping rule (`RunManifest.shipping_problems`: every gate
  cleared on the current zip, G0/G3/G5 real PASS, every task measured) enters `ledger/queue/`.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import math
import re
import shutil
import tempfile
import traceback
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ledger.archive import UnsafeArchive, safe_extract
from ledger.benchmark_health import PACKAGE_ROOT, is_circuit
from ledger.evidence import EVIDENCE_DIR, classify_submission
from ledger.run_manifest import (
    GATE_IDS,
    LEDGER_ROOT,
    MANIFESTS_DIR,
    REPO_ROOT,
    TASKS,
    GateRecord,
    ManifestError,
    Provenance,
    RunManifest,
    TaskRecord,
    _atomic_write_text,
    create_manifest,
    read_manifest,
    sha256_file,
    utc_now,
    write_index,
    write_manifest,
)

CONFIG_DIR = REPO_ROOT / "configs" / "gates"
DEFAULT_CONFIG = CONFIG_DIR / "default.yaml"
QUEUE_DIR = LEDGER_ROOT / "queue"

CheckFn = Callable[["GateContext"], dict[str, Any]]


class GateOrderError(RuntimeError):
    """An earlier gate has not been cleared on this zip."""


class GateNotWaivable(RuntimeError):
    """The config does not allow this gate to be waived, or no reason was given."""


class HookMissing(ImportError):
    """A configured `module:function` hook cannot be imported."""


@dataclass
class GateSpec:
    id: str
    name: str
    check: str
    waivable: bool = False
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class GateConfig:
    path: Path
    gates: list[GateSpec]
    salt_label: str | None = None
    generators: dict[str, list[str]] = field(default_factory=dict)
    # Declared competition-package inputs per task (`{"path": <relative>, "sha256": <hex>}`).
    # G5 stages only these into the generators' VQCC_DATA (PRA-211).
    inputs: dict[str, list[dict[str, str]]] = field(default_factory=dict)

    def spec(self, gate_id: str) -> GateSpec:
        for spec in self.gates:
            if spec.id == gate_id:
                return spec
        raise KeyError(f"gate {gate_id!r} is not in {self.path}")

    def earlier(self, gate_id: str) -> list[GateSpec]:
        ids = [g.id for g in self.gates]
        return self.gates[: ids.index(gate_id)]


@dataclass
class GateContext:
    manifest: RunManifest
    zip_path: Path
    submission_dir: Path
    config: GateConfig
    spec: GateSpec
    repo: Path = REPO_ROOT
    manifests_root: Path = MANIFESTS_DIR
    evidence_root: Path = EVIDENCE_DIR
    package_root: Path = PACKAGE_ROOT  # where G5 stages the declared inputs from

    @property
    def params(self) -> dict[str, Any]:
        return self.spec.params


def load_config(path: Path = DEFAULT_CONFIG) -> GateConfig:
    """Load and validate a gate config. The gates must be exactly G0..G5, in order."""
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if raw.get("schema") != 1:
        raise ValueError(f"{path}: unsupported gate config schema {raw.get('schema')!r}")
    gates = [GateSpec(**g) for g in raw["gates"]]
    ids = tuple(g.id for g in gates)
    if ids != GATE_IDS:
        raise ValueError(f"{path}: gates must be {GATE_IDS} in order, got {ids}")
    for g in gates:
        if ":" not in g.check:
            raise ValueError(f"{path}: {g.id} check {g.check!r} is not 'module:function'")
    for gate_id in ("G0", "G3", "G5"):
        if next(g for g in gates if g.id == gate_id).waivable:
            raise ValueError(f"{path}: {gate_id} can never be waivable")
    generators = raw.get("generators") or {}
    unknown = set(generators) - set(TASKS)
    if unknown:
        raise ValueError(f"{path}: generators for unknown tasks {sorted(unknown)}")
    inputs = raw.get("inputs") or {}
    unknown = set(inputs) - set(TASKS)
    if unknown:
        raise ValueError(f"{path}: inputs for unknown tasks {sorted(unknown)}")
    for task, entries in inputs.items():
        for entry in entries:
            rel = str(entry.get("path", ""))
            if not rel or rel.startswith(("/", "\\")) or ".." in Path(rel).parts:
                raise ValueError(f"{path}: {task} input path {rel!r} must be relative to the "
                                 "package root and contain no '..'")
            if not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", ""))):
                raise ValueError(f"{path}: {task} input {rel} needs a 64-hex sha256 pin")
            if is_circuit(rel):
                raise ValueError(f"{path}: {task} input {rel} is a circuit file; R10 requires every "
                                 "submitted circuit to be generated, so a circuit cannot be a "
                                 "declared input (D-PRA211-05)")
    return GateConfig(path=path, gates=gates, salt_label=raw.get("salt_label"),
                      generators=generators, inputs=inputs)


def resolve(ref: str) -> Callable[..., Any]:
    """Import `module:function`. A missing module or attribute raises HookMissing."""
    module_name, _, attr = ref.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise HookMissing(f"hook {ref} is not installed ({exc})") from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise HookMissing(f"hook {ref}: {module_name} has no {attr}") from exc


# --- Candidates -------------------------------------------------------------------------------


def start_candidate(
    zip_path: Path,
    candidate_id: str,
    provenance: dict[str, Provenance],
    *,
    parent_candidate_id: str | None = None,
    salt_label: str | None = None,
    repo: Path = REPO_ROOT,
    notes: str = "",
) -> RunManifest:
    """Create a candidate manifest from a zip: zip SHA-256 plus per-task file hashes."""
    missing = set(TASKS) - set(provenance)
    if missing:
        raise ManifestError(f"provenance missing for {sorted(missing)}")
    with tempfile.TemporaryDirectory(prefix="ledger-candidate-") as tmp:
        files = classify_submission(safe_extract(zip_path, Path(tmp) / "submission"))
    tasks = {
        t: TaskRecord(task=t, provenance=provenance[t], files=files[t]) for t in TASKS
    }
    return create_manifest(
        candidate_id=candidate_id,
        tasks=tasks,
        parent_candidate_id=parent_candidate_id,
        salt_label=salt_label,
        zip_sha256=sha256_file(zip_path),
        repo=repo,
        notes=notes,
    )


# --- Running gates ----------------------------------------------------------------------------


def check_order(manifest: RunManifest, gate_id: str, config: GateConfig) -> None:
    blocked = [g.id for g in config.earlier(gate_id) if not manifest.gate_cleared(g.id)]
    if blocked:
        raise GateOrderError(
            f"{manifest.candidate_id}: {gate_id} needs {', '.join(blocked)} cleared on zip "
            f"{(manifest.zip_sha256 or '')[:12]} first"
        )


def _bind_zip(manifest: RunManifest, zip_path: Path) -> None:
    actual = sha256_file(zip_path)
    if actual != manifest.zip_sha256:
        raise ManifestError(
            f"{zip_path} has SHA-256 {actual[:12]}, manifest is bound to "
            f"{(manifest.zip_sha256 or '')[:12]}"
        )


def run_gate(
    manifest: RunManifest,
    gate_id: str,
    zip_path: Path,
    submission_dir: Path,
    config: GateConfig,
    **context: Any,
) -> GateRecord:
    """Run one gate after checking the order; append and return its record.

    The check's result dict has `status` "PASS" or "FAIL: <reason>". Anything else, including an
    exception or a missing hook, is recorded as FAIL.
    """
    _bind_zip(manifest, zip_path)
    check_order(manifest, gate_id, config)
    spec = config.spec(gate_id)
    ctx = GateContext(manifest=manifest, zip_path=Path(zip_path),
                      submission_dir=Path(submission_dir), config=config, spec=spec, **context)
    try:
        result = resolve(spec.check)(ctx)
        status_text = str(result.get("status", "FAIL: check returned no status"))
    except Exception as exc:
        result = {"traceback": traceback.format_exc(limit=5)}
        status_text = f"FAIL: {type(exc).__name__}: {exc}"
    passed = status_text == "PASS"
    details = {k: v for k, v in result.items() if k not in ("status", "evidence_sha256")}
    record = GateRecord(
        gate=gate_id,
        status="PASS" if passed else "FAIL",
        timestamp_utc=utc_now(),
        zip_sha256=manifest.zip_sha256,
        reason="" if passed else status_text.removeprefix("FAIL: "),
        evidence_sha256=result.get("evidence_sha256"),
        details=_jsonable(details),
    )
    manifest.gates.append(record)
    return record


def waive_gate(manifest: RunManifest, gate_id: str, reason: str, config: GateConfig) -> GateRecord:
    spec = config.spec(gate_id)
    if not spec.waivable:
        raise GateNotWaivable(f"{gate_id} ({spec.name}) cannot be waived")
    if not reason.strip():
        raise GateNotWaivable(f"waiving {gate_id} needs a written reason")
    check_order(manifest, gate_id, config)
    record = GateRecord(gate=gate_id, status="WAIVED", timestamp_utc=utc_now(),
                        zip_sha256=manifest.zip_sha256, reason=reason.strip())
    manifest.gates.append(record)
    return record


def run_pipeline(
    manifest: RunManifest,
    zip_path: Path,
    config: GateConfig,
    *,
    waivers: dict[str, str] | None = None,
    stop_after: str | None = None,
    manifest_file: Path | None = None,
    queue_dir: Path = QUEUE_DIR,
    **context: Any,
) -> list[GateRecord]:
    """Run every gate not yet cleared on this zip, in order, stopping at the first FAIL.

    The manifest is rewritten after each gate when `manifest_file` is given, so a long G3 is not
    lost if a later step crashes. A G5 PASS enqueues the zip.
    """
    waivers = waivers or {}
    _bind_zip(manifest, zip_path)
    records: list[GateRecord] = []
    with tempfile.TemporaryDirectory(prefix="ledger-gates-") as tmp:
        submission_dir = Path(tmp) / "submission"
        try:
            safe_extract(zip_path, submission_dir)
        except (UnsafeArchive, zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError,
                ValueError) as exc:
            # Unsafe, corrupt, encrypted or unsupported archives are a G0 FAIL, not a crash.
            record = GateRecord(gate="G0", status="FAIL", timestamp_utc=utc_now(),
                                zip_sha256=manifest.zip_sha256,
                                reason=f"unusable zip: {type(exc).__name__}: {exc}")
            manifest.gates.append(record)
            _persist(manifest, manifest_file)
            return [record]
        for spec in config.gates:
            if manifest.gate_cleared(spec.id):
                continue
            if spec.id in waivers:
                record = waive_gate(manifest, spec.id, waivers[spec.id], config)
            else:
                record = run_gate(manifest, spec.id, zip_path, submission_dir, config, **context)
            records.append(record)
            _persist(manifest, manifest_file)
            if record.status == "FAIL" or spec.id == stop_after:
                break
    if not manifest.shipping_problems():
        enqueue(manifest, zip_path, queue_dir)
    return records


def rerun_gate(
    manifest: RunManifest,
    gate_id: str,
    zip_path: Path,
    config: GateConfig,
    *,
    generator_commit: str,
    note: str = "",
    manifest_file: Path | None = None,
    **context: Any,
) -> GateRecord:
    """Re-run one gate that has already run on a recorded manifest; append the record (PRA-211).

    Only G5 can be re-run: a decision may order the rebuild check to be repeated with the
    committed generators at `generator_commit`, which is recorded in the new record's
    `details.rebuild.commit`. The manifest's own `generator_commit` is never changed (it is part
    of the frozen index identity, PRA-210), earlier records stay as history, and nothing is
    queued. `note` is appended to the manifest notes. The order rule still applies: G0 to G4 must
    be cleared on this zip.
    """
    if gate_id != "G5":
        raise GateOrderError(f"only G5 can be re-run, not {gate_id}")
    if manifest.latest_gate(gate_id) is None:
        raise GateOrderError(f"{manifest.candidate_id}: {gate_id} has never run; use `run`")
    if not re.fullmatch(r"[0-9a-f]{40}", generator_commit or ""):
        raise ManifestError(f"generator commit {generator_commit!r} is not a clean 40-hex commit")
    _bind_zip(manifest, zip_path)
    # The check reads the generator commit from the manifest it is given; run it on a copy so the
    # recorded manifest keeps its identity and only gains the new record.
    probe = dataclasses.replace(manifest, generator_commit=generator_commit,
                                gates=list(manifest.gates))
    with tempfile.TemporaryDirectory(prefix="ledger-rerun-") as tmp:
        submission_dir = Path(tmp) / "submission"
        safe_extract(zip_path, submission_dir)
        record = run_gate(probe, gate_id, zip_path, submission_dir, config, **context)
    manifest.gates.append(record)
    if note:
        manifest.notes = f"{manifest.notes}\n{note}".strip()
    _persist(manifest, manifest_file)
    return record


def enqueue(manifest: RunManifest, zip_path: Path, queue_dir: Path = QUEUE_DIR) -> Path:
    """Copy a fully gated zip into the submission queue with a pointer file."""
    problems = manifest.shipping_problems()
    if problems:
        raise GateOrderError(f"{manifest.candidate_id} cannot be queued: {'; '.join(problems)}")
    _bind_zip(manifest, zip_path)
    queue_dir = Path(queue_dir)
    queue_dir.mkdir(parents=True, exist_ok=True)
    target = queue_dir / f"{manifest.candidate_id}.zip"
    shutil.copyfile(zip_path, target)
    pointer = {
        "candidate_id": manifest.candidate_id,
        "zip_sha256": manifest.zip_sha256,
        "geometric_mean": manifest.geometric_mean,
        "queued_at_utc": utc_now(),
    }
    _atomic_write_text(queue_dir / f"{manifest.candidate_id}.json",
                       json.dumps(pointer, indent=2, sort_keys=True) + "\n")
    return target


def _persist(manifest: RunManifest, manifest_file: Path | None) -> None:
    if manifest_file is not None:
        write_manifest(manifest, manifest_file)


def _jsonable(value: Any) -> Any:
    """Keep gate details JSON-safe (paths and other objects become strings)."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, float) and math.isnan(value):  # NaN is not valid JSON
        return None
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


# --- CLI --------------------------------------------------------------------------------------


def _load_provenance(path: Path) -> dict[str, Provenance]:
    raw = yaml.safe_load(Path(path).read_text())
    return {task: Provenance(**fields) for task, fields in raw.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the G0–G5 gates on a candidate zip")
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("new", help="create a candidate manifest from a zip")
    new.add_argument("--zip", type=Path, required=True)
    new.add_argument("--candidate-id", required=True)
    new.add_argument("--provenance", type=Path, required=True,
                     help="YAML: {task: {licence, parent_url, notes}}")
    new.add_argument("--parent", default=None)
    new.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    run = sub.add_parser("run", help="run the gates not yet cleared")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--zip", type=Path, required=True)
    run.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    run.add_argument("--waive", action="append", default=[], metavar="GATE=REASON")
    run.add_argument("--stop-after", default=None)
    rerun = sub.add_parser("rerun", help="re-run G5 on a recorded manifest with the generators at "
                                         "a named commit and append the record (PRA-211)")
    rerun.add_argument("--manifest", type=Path, required=True)
    rerun.add_argument("--zip", type=Path, required=True)
    rerun.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    rerun.add_argument("--gate", default="G5", choices=["G5"])
    rerun.add_argument("--generator-commit", required=True,
                       help="40-hex commit whose committed generators rebuild the files; recorded "
                            "in the new record, the manifest's generator_commit is unchanged")
    rerun.add_argument("--note", default="", help="appended to the manifest notes")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.command == "new":
        manifest = start_candidate(args.zip, args.candidate_id, _load_provenance(args.provenance),
                                   parent_candidate_id=args.parent, salt_label=config.salt_label)
        # Never overwrite an existing candidate's gate history.
        path = write_manifest(manifest, exclusive=True)
        write_index(path.parent.parent)  # derived, not committed (PRA-210)
        print(path)
        return 0
    manifest = read_manifest(args.manifest)
    if args.command == "rerun":
        record = rerun_gate(manifest, args.gate, args.zip, config,
                            generator_commit=args.generator_commit, note=args.note,
                            manifest_file=args.manifest)
        print(f"{record.gate} {record.status} {record.reason}".rstrip())
        print(json.dumps(record.details.get("rebuild", {}), indent=2, sort_keys=True, default=str))
        return 1 if record.status == "FAIL" else 0
    waivers = dict(w.split("=", 1) for w in args.waive)
    records = run_pipeline(manifest, args.zip, config, waivers=waivers,
                           stop_after=args.stop_after, manifest_file=args.manifest)
    for record in records:
        print(f"{record.gate} {record.status} {record.reason}".rstrip())
    return 1 if records and records[-1].status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
