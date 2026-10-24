from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import pytest
from conftest import git

from ledger.benchmark_health import EXAMPLES_DIR, run_benchmark_health
from ledger.run_manifest import (
    TASKS,
    GateRecord,
    ManifestError,
    Provenance,
    TaskRecord,
    append_to_index,
    compute_ratio,
    create_manifest,
    dumps,
    geometric_mean,
    git_commit_hash,
    loads,
    read_manifest,
    write_manifest,
)


def _tasks(cost: float = 2.0, baseline: float = 8.0) -> dict[str, TaskRecord]:
    return {
        t: TaskRecord(task=t, provenance=Provenance(licence="CC-BY-4.0",
                                                    parent_url="https://zenodo.org/x"),
                      files={f"{t}.kmb": "ab" * 32}, cost=cost, baseline_cost=baseline,
                      shots=10, failures=0, num_qubits=5, toffoli_count=7.5, measured=True,
                      metrics={"note": "x"}, evidence=["cd" * 32])
        for t in TASKS
    }


def test_manifest_round_trip(tmp_path: Path):
    manifest = create_manifest(candidate_id="c1", tasks=_tasks(), parent_candidate_id="c0",
                               salt_label="LOCAL", zip_sha256="ef" * 32,
                               kickmix_build_id="sha256:" + "0" * 64)
    manifest.gates.append(GateRecord(gate="G0", status="PASS", timestamp_utc="t",
                                     zip_sha256=manifest.zip_sha256, details={"n": 1}))
    path = write_manifest(manifest, tmp_path / "c1.json")
    again = read_manifest(path)
    assert again == manifest
    assert dumps(again) == path.read_text()
    assert again.geometric_mean == pytest.approx(4.0)
    data = json.loads(path.read_text())
    assert data["geometric_mean"] == pytest.approx(4.0)
    assert data["tasks"]["dqi"]["ratio"] == pytest.approx(4.0)
    assert again.gate_cleared("G0") and not again.gate_cleared("G1")


def test_ratios_are_recomputed_on_load():
    manifest = create_manifest(candidate_id="c1", tasks=_tasks())
    data = json.loads(dumps(manifest))
    data["tasks"]["invsqrt"]["ratio"] = 999.0
    data["geometric_mean"] = 999.0
    again = loads(json.dumps(data))
    assert again.tasks["invsqrt"].ratio == pytest.approx(4.0)
    assert again.geometric_mean == pytest.approx(4.0)


def test_geometric_mean_needs_all_three_tasks():
    tasks = _tasks()
    tasks["dqi"].cost = None
    assert create_manifest(candidate_id="c", tasks=tasks).geometric_mean is None
    del tasks["dqi"]
    assert create_manifest(candidate_id="c", tasks=tasks).geometric_mean is None


def test_arithmetic():
    assert compute_ratio(10.0, 4.0) == 2.5
    assert compute_ratio(None, 4.0) is None
    assert compute_ratio(10.0, 0.0) is None
    assert compute_ratio(10.0, math.inf) is None
    assert geometric_mean([8.0, 1.0, 1.0]) == pytest.approx(2.0)
    with pytest.raises(ValueError):
        geometric_mean([1.0, 0.0])


@pytest.mark.parametrize("mutate, message", [
    (lambda t: setattr(t["dqi"].provenance, "licence", "MIT"), "not in"),
    (lambda t: setattr(t["dqi"].provenance, "parent_url", None), "needs a parent_url"),
    (lambda t: t["dqi"].files.update({"dqi.kmb": "xyz"}), "malformed SHA-256"),
    (lambda t: t.update(bogus=TaskRecord(task="bogus", provenance=Provenance("own"))),
     "unknown task"),
])
def test_validation_rejects_bad_records(mutate, message):
    tasks = _tasks()
    mutate(tasks)
    with pytest.raises(ManifestError, match=message):
        create_manifest(candidate_id="c", tasks=tasks)


def test_own_code_needs_no_parent_url():
    tasks = _tasks()
    tasks["invsqrt"].provenance = Provenance(licence="own")
    create_manifest(candidate_id="c", tasks=tasks)


def test_submission_manifest_needs_kaggle_id_and_source():
    manifest = create_manifest(candidate_id="c", tasks=_tasks())
    manifest.kind = "submission"
    with pytest.raises(ManifestError, match="kaggle_submission_id"):
        write_manifest(manifest, Path("/nonexistent/never-written.json"))


def test_git_commit_hash_marks_dirty_worktrees(tmp_path: Path):
    git(tmp_path, "init", "-q")
    (tmp_path / "a.txt").write_text("a")
    git(tmp_path, "add", "a.txt")
    git(tmp_path, "commit", "-qm", "a")
    head = git(tmp_path, "rev-parse", "HEAD")
    assert git_commit_hash(tmp_path) == head
    (tmp_path / "a.txt").write_text("b")
    assert git_commit_hash(tmp_path) == f"{head}-dirty"


def test_index_csv_appends_with_one_header(tmp_path: Path):
    index = tmp_path / "index.csv"
    for i in range(2):
        append_to_index(create_manifest(candidate_id=f"c{i}", tasks=_tasks()), index)
    rows = list(csv.DictReader(index.open()))
    assert [r["candidate_id"] for r in rows] == ["c0", "c1"]
    assert float(rows[0]["geometric_mean"]) == pytest.approx(4.0)


def test_reference_example_manifest():
    """The committed sample manifest for the reference submission parses, scores 1.0, and
    says honestly which tasks were measured."""
    manifest = read_manifest(EXAMPLES_DIR / "reference-submission.json")
    assert manifest.candidate_id == "reference"
    assert manifest.geometric_mean == pytest.approx(1.0)
    assert manifest.tasks["invsqrt"].measured and manifest.tasks["dfthcsos"].measured
    assert not manifest.tasks["dqi"].measured and not manifest.is_measured()
    assert manifest.tasks["invsqrt"].cost == pytest.approx(2076774.233715282)
    assert manifest.tasks["invsqrt"].failures == 0
    assert manifest.tasks["invsqrt"].shots == 200540928
    assert manifest.tasks["dfthcsos"].cost == pytest.approx(3355599588.3155365)
    assert manifest.tasks["dfthcsos"].num_qubits == 730
    assert manifest.tasks["dqi"].files == {
        "dqi.kmb": "959471d05a26373b4f14ca0cae2d8639ea25f18170d9f6532139aa51ccc04995"}
    assert len(manifest.tasks["dfthcsos"].files) == 11
    # The evidence record named in the manifest exists and hashes to the recorded SHA-256.
    from ledger.run_manifest import sha256_file

    evidence = EXAMPLES_DIR / "reference" / "evidence" / "reference" / "reference-baseline.json"
    assert manifest.tasks["invsqrt"].evidence == [sha256_file(evidence)]
    for log in json.loads(evidence.read_text())["logs"]:
        assert sha256_file(EXAMPLES_DIR / log["path"]) == log["sha256"]


def test_benchmark_health_self_checks_pass():
    report = run_benchmark_health()
    assert report["overall"] == "PASS", report


def test_decisions_register_holds_the_rulings():
    from ledger.run_manifest import REPO_ROOT

    rows = [line for line in (REPO_ROOT / "docs" / "DECISIONS.md").read_text().splitlines()
            if line.startswith("| 20")]
    ids = [row.split("|")[2].strip() for row in rows]
    assert ids[0] == "D-001"  # append-only: the first row is never rewritten
    for n in range(1, 13):
        assert ids.count(f"R{n}") == 1, f"R{n}"
    assert len(ids) == len(set(ids))
