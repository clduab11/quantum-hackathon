"""G5 path for a vendored Apache-2.0 circuit (D-PRA341-01).

A declared input of kind ``vendored_circuit`` may be a circuit. G5 passes that task only when
the shipped file matches the pinned source byte for byte and the licence-record ticket is set.
``shipping_problems`` names a vendored circuit that has no licence record. A circuit copy that
is not declared ``vendored_circuit`` still fails, as it did under D-PRA211-05.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import git
from ledger.archive import build_zip
from ledger.gates.runner import GATE_IDS, load_config, run_pipeline, start_candidate
from ledger.run_manifest import (
    GATE_IDS as MANIFEST_GATES,
    GateRecord,
    Provenance,
    TaskRecord,
    create_manifest,
)

SOURCE_REL = "vendored/invsqrt.kmb"
SOURCE_URL = "https://example.invalid/circuits/invsqrt"
SOURCE_BYTES = b"frozen apache-2.0 circuit v1"
VENDOR = '''\
import os, shutil, sys
from pathlib import Path
task, out = sys.argv[1], Path(sys.argv[2])
mode = sys.argv[3] if len(sys.argv) > 3 else "copy"
if task != "invsqrt":
    raise SystemExit(0)
path = out / "invsqrt.kmb"
path.parent.mkdir(parents=True, exist_ok=True)
if mode == "change":
    path.write_bytes(b"changed-circuit")
else:
    shutil.copyfile(Path(os.environ["VQCC_DATA"]) / "vendored" / "invsqrt.kmb", path)
'''


def _vendored_entry(*, licence_record: str = "PRA-325", sha256: str | None = None,
                    source_url: str = SOURCE_URL, licence: str = "Apache-2.0") -> dict[str, str]:
    return {
        "kind": "vendored_circuit",
        "path": SOURCE_REL,
        "sha256": sha256 or hashlib.sha256(SOURCE_BYTES).hexdigest(),
        "source_url": source_url,
        "version": "1.0.0",
        "licence": licence,
        "licence_record": licence_record,
    }


def _config(workspace, entry: dict[str, str], mode: str):
    raw = yaml.safe_load(workspace.config.path.read_text())
    raw["generators"]["invsqrt"] = ["{python}", "vendor.py", "invsqrt", "{out}", mode]
    raw["inputs"] = {"invsqrt": [entry]}
    path = workspace.root / f"vendored-{mode}-{entry.get('licence_record', 'none')}.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return load_config(path)


def _prepare(workspace, mode: str) -> None:
    source = workspace.package_root / SOURCE_REL
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(SOURCE_BYTES)
    script = workspace.repo / "vendor.py"
    if not script.exists():
        script.write_text(VENDOR)
        git(workspace.repo, "add", "vendor.py")
        git(workspace.repo, "commit", "-q", "-m", "toy vendored-circuit generator")


def _zip(workspace, mode: str) -> Path:
    built = workspace.root / f"built-{mode}"
    env = {**os.environ, "VQCC_DATA": str(workspace.package_root)}
    subprocess.run([sys.executable, "vendor.py", "invsqrt", str(built), mode], cwd=workspace.repo,
                   check=True, env=env)
    for task in ("dqi", "dfthcsos"):
        subprocess.run([sys.executable, "gen.py", task, str(built)], cwd=workspace.repo, check=True)
    return build_zip(built, workspace.root / f"{mode}.zip")


def _run(workspace, mode: str, entry: dict[str, str], candidate_id: str):
    _prepare(workspace, mode)
    config = _config(workspace, entry, mode)
    zip_path = _zip(workspace, mode)
    provenance = {t: Provenance(licence="Apache-2.0", parent_url="https://example.invalid/p")
                  for t in ("invsqrt", "dqi", "dfthcsos")}
    manifest = start_candidate(zip_path, candidate_id, provenance, salt_label=config.salt_label,
                               repo=workspace.repo)
    records = run_pipeline(manifest, zip_path, config, queue_dir=workspace.queue_dir,
                           **workspace.context())
    return manifest, records


def test_g5_passes_a_vendored_circuit_with_matching_bytes_and_a_licence_record(workspace, fakes):
    manifest, records = _run(workspace, "copy", _vendored_entry(), "vendored-ok")
    assert [(r.gate, r.status) for r in records] == [(g, "PASS") for g in GATE_IDS], records
    rebuild = manifest.latest_gate("G5").details["rebuild"]
    assert rebuild["vendored_circuits"] == {"invsqrt.kmb": SOURCE_REL}
    assert rebuild["tasks"]["invsqrt"]["identical"] is True
    assert manifest.shipping_problems() == []
    assert (workspace.queue_dir / "vendored-ok.zip").exists()


def test_g5_fails_when_the_vendored_circuit_bytes_change(workspace, fakes):
    manifest, records = _run(workspace, "change", _vendored_entry(), "vendored-changed")
    assert records[-1].gate == "G5" and records[-1].status == "FAIL", records
    assert "not byte-identical to the pinned source" in records[-1].reason
    assert not (workspace.queue_dir / "vendored-changed.zip").exists()


def test_missing_licence_record_is_a_shipping_problem(workspace, fakes):
    manifest, records = _run(workspace, "copy", _vendored_entry(licence_record=""), "vendored-nolicence")
    assert records[-1].gate == "G5" and records[-1].status == "FAIL"
    assert "no licence record" in records[-1].reason
    problems = manifest.shipping_problems()
    assert any("vendored_circuit" in p and "no licence record" in p for p in problems), problems
    assert not (workspace.queue_dir / "vendored-nolicence.zip").exists()


def test_shipping_problems_names_only_the_vendored_circuit_that_lacks_a_licence_record():
    """A manifest that otherwise may ship still reports the blank licence record, and clears
    that report once the ticket id is set."""
    tasks = {
        t: TaskRecord(task=t, provenance=Provenance(licence="own"), files={f"{t}.kmb": "ab" * 32},
                      cost=2.0, baseline_cost=4.0, measured=True)
        for t in ("invsqrt", "dqi", "dfthcsos")
    }
    manifest = create_manifest(candidate_id="ship-check", tasks=tasks, zip_sha256="cd" * 32)
    manifest.gates = [
        GateRecord(gate=g, status="PASS", timestamp_utc="t", zip_sha256=manifest.zip_sha256)
        for g in MANIFEST_GATES
    ]
    manifest.declared_inputs = {"invsqrt": [_vendored_entry(licence_record="")]}
    problems = manifest.shipping_problems()
    assert problems == ["vendored_circuit invsqrt vendored/invsqrt.kmb has no licence record"]
    manifest.declared_inputs["invsqrt"][0]["licence_record"] = "PRA-325"
    assert manifest.shipping_problems() == []


def test_an_undeclared_circuit_copy_still_fails_g5(workspace, fakes):
    config = workspace.copier_config(copy_as_circuit=True)
    zip_path = workspace.copier_zip("undeclared", copy_as_circuit=True)
    provenance = {t: Provenance(licence="Apache-2.0", parent_url="https://example.invalid/p")
                  for t in ("invsqrt", "dqi", "dfthcsos")}
    manifest = start_candidate(zip_path, "undeclared-copy", provenance,
                               salt_label=config.salt_label, repo=workspace.repo)
    records = run_pipeline(manifest, zip_path, config, queue_dir=workspace.queue_dir,
                           **workspace.context())
    assert records[-1].gate == "G5" and records[-1].status == "FAIL", records
    assert "copied competition-package circuits, not generated (R10)" in records[-1].reason
    assert not (workspace.queue_dir / "undeclared-copy.zip").exists()


def test_a_circuit_without_vendored_kind_is_still_rejected(tmp_path):
    from ledger.benchmark_health import InputError, stage_inputs
    from ledger.gates.runner import DEFAULT_CONFIG

    package = tmp_path / "package"
    (package / "sample_submission").mkdir(parents=True)
    (package / "sample_submission" / "invsqrt.kmb").write_bytes(b"circuit")
    digest = hashlib.sha256(b"circuit").hexdigest()
    entry = {"path": "sample_submission/invsqrt.kmb", "sha256": digest}
    with pytest.raises(InputError, match="circuit file"):
        stage_inputs({"invsqrt": [entry]}, tmp_path / "staging", package)
    raw = yaml.safe_load(DEFAULT_CONFIG.read_text())
    raw["inputs"] = {"invsqrt": [entry]}
    path = tmp_path / "gates.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="circuit file"):
        load_config(path)


@pytest.mark.parametrize("mutate, message", [
    (lambda e: e.update(source_url="https://github.com/jday96314/QuantumAI"), "jday96314"),
    (lambda e: e.update(source_url="https://k256.dev/dqi/artifact"), "k256.dev"),
    (lambda e: e.update(licence="no-licence"), "no-licence"),
    (lambda e: e.update(licence="reference-only"), "reference-only"),
    (lambda e: e.update(path="vendored/factor.npz"), "circuit file"),
    (lambda e: e.pop("source_url"), "source_url"),
    (lambda e: e.update(version=""), "version"),
])
def test_banned_or_incomplete_vendored_sources_are_rejected(tmp_path, mutate, message):
    from ledger.gates.runner import DEFAULT_CONFIG

    entry = _vendored_entry()
    mutate(entry)
    raw = yaml.safe_load(DEFAULT_CONFIG.read_text())
    raw["inputs"] = {"invsqrt": [entry]}
    path = tmp_path / "gates.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match=message):
        load_config(path)
