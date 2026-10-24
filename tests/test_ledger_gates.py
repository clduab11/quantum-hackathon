from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from ledger.archive import safe_extract
from ledger.gates.runner import (
    DEFAULT_CONFIG,
    GATE_IDS,
    GateNotWaivable,
    GateOrderError,
    enqueue,
    load_config,
    run_gate,
    run_pipeline,
    waive_gate,
)
from ledger.run_manifest import GateRecord, ManifestError, write_manifest


def _run(ws, manifest, gate):
    with tempfile.TemporaryDirectory() as tmp:
        submission = safe_extract(ws.zip_path, Path(tmp) / "s")
        return run_gate(manifest, gate, ws.zip_path, submission, ws.config, **ws.context())


def _pipeline(ws, manifest, **kwargs):
    return run_pipeline(manifest, ws.zip_path, ws.config, queue_dir=ws.queue_dir,
                        **ws.context(), **kwargs)


# --- Config -----------------------------------------------------------------------------------


def test_default_config_loads_in_order():
    config = load_config(DEFAULT_CONFIG)
    assert tuple(g.id for g in config.gates) == GATE_IDS
    assert {g.id for g in config.gates if not g.waivable} == {"G0", "G3", "G5"}
    assert config.spec("G3").params["expected_shots"] == {
        "invsqrt": 200540928, "dqi": 102400, "dfthcsos": 254464}


@pytest.mark.parametrize("mutate, message", [
    (lambda raw: raw["gates"].reverse(), "in order"),
    (lambda raw: raw["gates"].pop(2), "in order"),
    (lambda raw: raw["gates"][3].update(waivable=True), "G3 can never be waivable"),
    (lambda raw: raw["gates"][0].update(check="no_colon"), "module:function"),
])
def test_bad_configs_are_rejected(tmp_path, mutate, message):
    raw = yaml.safe_load(DEFAULT_CONFIG.read_text())
    mutate(raw)
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match=message):
        load_config(path)


# --- Ordering ---------------------------------------------------------------------------------


def test_cannot_reach_g3_without_g2(workspace, fakes):
    manifest = workspace.candidate()
    assert _run(workspace, manifest, "G0").status == "PASS"
    assert _run(workspace, manifest, "G1").status == "PASS"
    with pytest.raises(GateOrderError, match="G3 needs G2"):
        _run(workspace, manifest, "G3")
    assert "g3" not in fakes.CALLS


def test_failed_g2_blocks_g3(workspace, fakes):
    fakes.BEHAVIOUR["g2"] = "FAIL: proxy mismatch at x=17"
    manifest = workspace.candidate()
    records = _pipeline(workspace, manifest)
    assert [(r.gate, r.status) for r in records] == [
        ("G0", "PASS"), ("G1", "PASS"), ("G2", "FAIL")]
    assert "proxy mismatch at x=17" in records[-1].reason
    assert "g3" not in fakes.CALLS
    with pytest.raises(GateOrderError):
        _run(workspace, manifest, "G3")


def test_gate_results_are_bound_to_the_zip(workspace, fakes):
    manifest = workspace.candidate()
    _pipeline(workspace, manifest, stop_after="G2")
    assert manifest.gate_cleared("G2")
    # A different zip invalidates the earlier gates: G3 may not run on it.
    manifest.zip_sha256 = "f" * 64
    assert not manifest.gate_cleared("G2")
    with pytest.raises(ManifestError, match="bound to"):
        _run(workspace, manifest, "G3")


def test_hook_exceptions_and_missing_hooks_fail(workspace, fakes, tmp_path):
    fakes.BEHAVIOUR["g0"] = ValueError("invsqrt must have exactly one named register.")
    manifest = workspace.candidate()
    record = _run(workspace, manifest, "G0")
    assert record.status == "FAIL"
    assert "exactly one named register" in record.reason

    raw = yaml.safe_load(workspace.config.path.read_text())
    raw["gates"][1]["params"]["hooks"].pop("dqi")
    raw["gates"][0]["params"]["hook"] = "not_installed_module:preflight"
    path = tmp_path / "missing.yaml"
    path.write_text(yaml.safe_dump(raw))
    workspace.config = load_config(path)
    fakes.BEHAVIOUR.clear()
    record = _run(workspace, manifest, "G0")
    assert record.status == "FAIL" and "not installed" in record.reason


def test_per_task_gate_needs_a_hook_for_every_task(workspace, fakes, tmp_path):
    raw = yaml.safe_load(workspace.config.path.read_text())
    raw["gates"][1]["params"]["hooks"].pop("dqi")
    path = tmp_path / "g1.yaml"
    path.write_text(yaml.safe_dump(raw))
    workspace.config = load_config(path)
    manifest = workspace.candidate()
    records = _pipeline(workspace, manifest)
    assert records[-1].gate == "G1" and records[-1].status == "FAIL"
    assert "no G1 hook configured for dqi" in records[-1].reason


# --- Waivers ----------------------------------------------------------------------------------


def test_only_waivable_gates_with_reasons_can_be_waived(workspace):
    manifest = workspace.candidate()
    with pytest.raises(GateNotWaivable):
        waive_gate(manifest, "G0", "trust me", workspace.config)
    with pytest.raises(GateNotWaivable, match="reason"):
        waive_gate(manifest, "G1", "  ", workspace.config)
    with pytest.raises(GateOrderError):
        waive_gate(manifest, "G1", "smoke not written yet", workspace.config)


def test_waived_gates_clear_the_way_and_are_recorded(workspace, fakes):
    manifest = workspace.candidate()
    records = _pipeline(workspace, manifest, waivers={"G1": "no smoke instance yet"},
                        stop_after="G2")
    assert [(r.gate, r.status) for r in records] == [
        ("G0", "PASS"), ("G1", "WAIVED"), ("G2", "PASS")]
    assert manifest.latest_gate("G1").reason == "no smoke instance yet"
    assert "g1" not in fakes.CALLS


# --- G3, G4, G5 and the queue -----------------------------------------------------------------


def test_full_pipeline_reaches_the_queue(workspace, fakes):
    manifest = workspace.candidate()
    manifest_file = workspace.manifests_root / "candidates" / "cand-001.json"
    records = _pipeline(workspace, manifest, manifest_file=manifest_file)
    assert [(r.gate, r.status) for r in records] == [(g, "PASS") for g in GATE_IDS], records
    assert fakes.CALLS == ["g0", "g1", "g1", "g1", "g2", "g2", "g2", "g3"]
    assert manifest.is_measured()
    assert manifest.geometric_mean == pytest.approx(2.0)
    assert manifest.tasks["dqi"].failures == 1
    assert manifest.latest_gate("G3").evidence_sha256 in manifest.tasks["invsqrt"].evidence
    assert manifest.latest_gate("G5").details["rebuild"]["status"] == "PASS"
    assert (workspace.queue_dir / "cand-001.zip").read_bytes() == workspace.zip_path.read_bytes()
    pointer = json.loads((workspace.queue_dir / "cand-001.json").read_text())
    assert pointer["zip_sha256"] == manifest.zip_sha256
    # The manifest on disk was kept up to date gate by gate.
    on_disk = json.loads(manifest_file.read_text())
    assert [g["gate"] for g in on_disk["gates"]] == list(GATE_IDS)
    # Re-running is a no-op: every gate is already cleared on this zip.
    assert _pipeline(workspace, manifest) == []


def test_g3_rejects_short_shot_counts(workspace, fakes):
    result = fakes.g3(None, salt_label=None)
    result["tasks"]["dqi"]["verified_shots"] = 1024
    fakes.BEHAVIOUR["g3"] = result
    fakes.CALLS.clear()
    manifest = workspace.candidate()
    records = _pipeline(workspace, manifest)
    assert records[-1].gate == "G3" and records[-1].status == "FAIL"
    assert "dqi: 1024 shots, expected 102400" in records[-1].reason
    assert not manifest.is_measured()


def test_g4_needs_strict_improvement_over_parent_and_archive(workspace, fakes):
    parent = workspace.candidate("parent")
    _pipeline(workspace, parent, stop_after="G4")
    assert parent.gate_cleared("G4")  # first measured candidate: nothing to beat
    write_manifest(parent, workspace.manifests_root / "candidates" / "parent.json")

    fakes.BEHAVIOUR["g3_divisor"] = 2.0  # same score as the parent: not strictly better
    child = workspace.candidate("child", parent="parent")
    records = _pipeline(workspace, child)
    assert records[-1].gate == "G4" and records[-1].status == "FAIL"
    assert "does not beat parent" in records[-1].reason

    fakes.BEHAVIOUR["g3_divisor"] = 2.5
    better = workspace.candidate("better", parent="parent")
    records = _pipeline(workspace, better, stop_after="G4")
    assert records[-1].status == "PASS"
    assert better.latest_gate("G4").details["archive_best"]["candidate_id"] == "parent"


def test_g4_fails_for_unknown_parent(workspace, fakes):
    orphan = workspace.candidate("orphan", parent="missing-parent")
    records = _pipeline(workspace, orphan)
    assert records[-1].gate == "G4" and "missing-parent" in records[-1].reason


def test_g5_rejects_reference_only_provenance(workspace, fakes):
    manifest = workspace.candidate(licence="reference-only")
    records = _pipeline(workspace, manifest)
    assert records[-1].gate == "G5" and records[-1].status == "FAIL"
    assert "cannot be shipped (R10)" in records[-1].reason
    assert not (workspace.queue_dir / "cand-001.zip").exists()


def test_g5_rejects_a_dirty_generator_commit(workspace, fakes):
    (workspace.repo / "uncommitted.txt").write_text("local edit")
    manifest = workspace.candidate()
    assert manifest.generator_commit.endswith("-dirty")
    records = _pipeline(workspace, manifest)
    assert records[-1].gate == "G5" and "not a clean 40-hex commit" in records[-1].reason


def test_g5_detects_a_generator_that_no_longer_reproduces(workspace, fakes):
    manifest = workspace.candidate()
    gen = workspace.repo / "gen.py"
    gen.write_text(gen.read_text().replace('"generated "', '"changed "'))
    from conftest import git

    git(workspace.repo, "commit", "-qam", "generator drift")
    manifest.generator_commit = git(workspace.repo, "rev-parse", "HEAD")
    records = _pipeline(workspace, manifest)
    assert records[-1].gate == "G5" and records[-1].status == "FAIL"
    assert "rebuild differs for" in records[-1].reason
    rebuild = manifest.latest_gate("G5").details["rebuild"]
    assert rebuild["tasks"]["invsqrt"]["diffs"]["changed"] == ["invsqrt.kmb"]


def test_enqueue_refuses_without_g5(workspace):
    manifest = workspace.candidate()
    manifest.gates.append(GateRecord(gate="G4", status="PASS", timestamp_utc="",
                                     zip_sha256=manifest.zip_sha256))
    with pytest.raises(GateOrderError, match="G5 not cleared"):
        enqueue(manifest, workspace.zip_path, workspace.queue_dir)


def test_unsafe_zip_fails_g0(workspace, tmp_path):
    import zipfile

    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("../escape.kmb", b"x")
    manifest = workspace.candidate()
    from ledger.run_manifest import sha256_file

    manifest.zip_sha256 = sha256_file(bad)
    records = run_pipeline(manifest, bad, workspace.config, queue_dir=workspace.queue_dir,
                           **workspace.context())
    assert [(r.gate, r.status) for r in records] == [("G0", "FAIL")]
    assert "unsafe path" in records[0].reason


def test_corrupt_zip_is_a_g0_fail_not_a_crash(workspace, tmp_path):
    from ledger.run_manifest import sha256_file

    corrupt = tmp_path / "corrupt.zip"
    corrupt.write_bytes(b"PK\x03\x04 this is not really a zip")
    manifest = workspace.candidate()
    manifest.zip_sha256 = sha256_file(corrupt)
    records = run_pipeline(manifest, corrupt, workspace.config, queue_dir=workspace.queue_dir,
                           **workspace.context())
    assert [(r.gate, r.status) for r in records] == [("G0", "FAIL")]
    assert "BadZipFile" in records[0].reason


def test_new_candidate_never_overwrites_an_existing_one(workspace, tmp_path, monkeypatch):
    from ledger.gates import runner

    manifest = workspace.candidate()
    path = tmp_path / "manifests" / "candidates" / "cand-001.json"
    write_manifest(manifest, path, exclusive=True)
    with pytest.raises(FileExistsError):
        write_manifest(workspace.candidate(), path, exclusive=True)
    assert runner.read_manifest(path) == manifest
