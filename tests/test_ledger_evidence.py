from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import ledger_fakes
import pytest

from ledger.archive import UnsafeArchive, build_zip, safe_extract
from ledger.benchmark_health import EXAMPLES_DIR
from ledger.evidence import (
    EvidenceError,
    apply_verifier_summary,
    classify_submission,
    collect_verifier_evidence,
    load_summary,
)
from ledger.run_manifest import TASKS, Provenance, TaskRecord, create_manifest, sha256_file

LOGS = EXAMPLES_DIR / "reference" / "logs"


def _record(task: str) -> TaskRecord:
    return TaskRecord(task=task, provenance=Provenance(licence="own"))


def test_real_invsqrt_summary_maps_to_the_record():
    record = apply_verifier_summary(_record("invsqrt"), load_summary(LOGS / "invsqrt.json"),
                                    baseline_cost=2076774.233715282)
    assert record.measured
    assert record.cost == pytest.approx(2076774.233715282)
    assert (record.num_qubits, record.toffoli_count, record.t_count) == (260, 7735.0, 1.0)
    assert record.rotation_count == 37.0 and record.failures == 0
    assert record.shots == 200540928
    assert record.ratio == pytest.approx(1.0)
    assert record.metrics["circuit_sha256"].startswith("e2bf8eb6")


def test_real_dfthcsos_summary_maps_to_the_record():
    record = apply_verifier_summary(_record("dfthcsos"), load_summary(LOGS / "dfthcsos.json"))
    assert record.cost == pytest.approx(3355599588.3155365)
    assert (record.num_qubits, record.toffoli_count) == (730, 93237.0)
    assert record.metrics["lambda_eff"] == pytest.approx(49.30136925057438)
    assert record.metrics["Lambda"] == pytest.approx(308.4559397330944)
    assert record.metrics["E_gap"] == pytest.approx(3.965477244291833)
    assert record.metrics["angles_qubits"] == 119
    assert record.shots == 254464


def test_dqi_summary_counts_both_error_kinds():
    record = apply_verifier_summary(_record("dqi"), ledger_fakes.summaries()["dqi"])
    assert record.failures == 1 and record.eps_plus == pytest.approx(0.0017)


def test_failed_verification_is_never_recorded_as_measured():
    record = _record("dqi")
    with pytest.raises(EvidenceError, match="Effective error rate"):
        apply_verifier_summary(record, {"status": "FAIL",
                                        "error": "Effective error rate 0.07 >= 1/16"})
    assert not record.measured and record.cost is None


def _tree(root: Path, names: list[str]) -> Path:
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
    return root


def test_classify_submission(tmp_path: Path):
    root = _tree(tmp_path / "s", ["sub/invsqrt.kmb", "dqi.kmx", "dfthcsos/angle_k_0.kmb",
                                  "dfthcsos/submission.npz", "__MACOSX/dqi.kmb"])
    files = classify_submission(root)
    assert set(files) == set(TASKS)
    assert list(files["invsqrt"]) == ["sub/invsqrt.kmb"]
    assert list(files["dqi"]) == ["dqi.kmx"]
    assert sorted(files["dfthcsos"]) == ["dfthcsos/angle_k_0.kmb", "dfthcsos/submission.npz"]
    _tree(root, ["other/invsqrt.kmx"])
    with pytest.raises(EvidenceError, match="exactly one invsqrt"):
        classify_submission(root)


def test_collect_verifier_evidence_chains_hashes(tmp_path: Path):
    tasks = {t: _record(t) for t in TASKS}
    manifest = create_manifest(candidate_id="c1", tasks=tasks, zip_sha256="ab" * 32)
    log = tmp_path / "run.log"
    log.write_text("verifier output\n")
    digest = collect_verifier_evidence(
        manifest, "G3", ledger_fakes.summaries(), logs=[log], log_root=tmp_path,
        baseline_costs=ledger_fakes.BASELINES, root=tmp_path / "evidence")
    path = tmp_path / "evidence" / "c1" / "G3.json"
    assert sha256_file(path) == digest
    record = json.loads(path.read_text())
    assert record["logs"] == [{"path": "run.log", "sha256": sha256_file(log), "bytes": 16}]
    assert all(manifest.tasks[t].evidence == [digest] for t in TASKS)
    assert manifest.geometric_mean == pytest.approx(2.0)


def test_a_failure_part_way_leaves_no_task_measured(tmp_path: Path):
    tasks = {t: _record(t) for t in TASKS}
    manifest = create_manifest(candidate_id="c1", tasks=tasks, zip_sha256="ab" * 32)
    summaries = ledger_fakes.summaries()
    del summaries["dfthcsos"]["score"]  # the last task breaks after the first two applied
    with pytest.raises(KeyError):
        collect_verifier_evidence(manifest, "G3", summaries, root=tmp_path / "evidence")
    assert not any(manifest.tasks[t].measured for t in TASKS)
    nan = ledger_fakes.summaries()
    nan["dqi"]["mean_error_weight"] = float("nan")  # evidence cannot be written as JSON
    with pytest.raises(ValueError):
        collect_verifier_evidence(manifest, "G3", nan, root=tmp_path / "evidence")
    assert not any(manifest.tasks[t].measured for t in TASKS)
    assert manifest.tasks["invsqrt"].cost is None


def test_build_zip_is_deterministic(tmp_path: Path):
    src = _tree(tmp_path / "s", ["invsqrt.kmb", "dfthcsos/angle_k_0.kmb"])
    first = sha256_file(build_zip(src, tmp_path / "a.zip"))
    os.utime(src / "invsqrt.kmb", (0, 0))
    (src / "dfthcsos" / "angle_k_0.kmb").chmod(0o600)
    assert sha256_file(build_zip(src, tmp_path / "b.zip")) == first
    out = safe_extract(tmp_path / "b.zip", tmp_path / "x")
    assert (out / "dfthcsos" / "angle_k_0.kmb").read_bytes() == b"dfthcsos/angle_k_0.kmb"


@pytest.mark.parametrize("name", ["../escape.kmb", "/abs.kmb", "dir\\file.kmb"])
def test_safe_extract_rejects_unsafe_paths(tmp_path: Path, name: str):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr(name, b"x")
    with pytest.raises(UnsafeArchive, match="unsafe path"):
        safe_extract(bad, tmp_path / "out")


def test_safe_extract_rejects_links_and_duplicates(tmp_path: Path):
    link = tmp_path / "link.zip"
    with zipfile.ZipFile(link, "w") as archive:
        info = zipfile.ZipInfo("dqi.kmb")
        info.external_attr = 0o120777 << 16  # symlink
        archive.writestr(info, "/etc/passwd")
    with pytest.raises(UnsafeArchive, match="link or special file"):
        safe_extract(link, tmp_path / "out1")
    for alias in ("./dqi.kmb", "sub//dqi.kmb"):
        aliased = tmp_path / f"alias{len(alias)}.zip"
        with zipfile.ZipFile(aliased, "w") as archive:
            archive.writestr(alias.replace("./", "").replace("//", "/"), b"1")
            archive.writestr(alias, b"2")
        with pytest.raises(UnsafeArchive, match="duplicate"):
            safe_extract(aliased, tmp_path / f"out-{len(alias)}")
    dup = tmp_path / "dup.zip"
    with zipfile.ZipFile(dup, "w") as archive:
        archive.writestr("dqi.kmb", b"1")
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("dqi.kmb", b"2")
    with pytest.raises(UnsafeArchive, match="duplicate"):
        safe_extract(dup, tmp_path / "out2")
