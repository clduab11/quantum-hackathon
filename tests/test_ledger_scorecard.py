from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ledger.run_manifest import (
    GATE_IDS,
    TASKS,
    GateRecord,
    ManifestError,
    Provenance,
    TaskRecord,
    create_manifest,
    load_manifests,
    write_manifest,
)
from ledger.scorecard import (
    DAILY_CAP,
    SubmissionCapExceeded,
    assert_slot_available,
    best_geometric_mean,
    best_per_task,
    main,
    record_submission,
    render_markdown,
    slots_left,
    submissions_per_utc_day,
    utc_day,
)

NOON = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def _candidate(candidate_id: str = "cand", ratio: float = 2.0, measured: bool = True,
               g5: bool = True):
    tasks = {t: TaskRecord(task=t, provenance=Provenance(licence="own"), cost=1.0,
                           baseline_cost=ratio, measured=measured) for t in TASKS}
    manifest = create_manifest(candidate_id=candidate_id, tasks=tasks, zip_sha256="ab" * 32)
    for gate in GATE_IDS if g5 else GATE_IDS[:-1]:
        manifest.gates.append(GateRecord(gate=gate, status="PASS", timestamp_utc="",
                                         zip_sha256=manifest.zip_sha256))
    return manifest


def _files(root: Path) -> list[str]:
    return sorted(p.name for p in (root / "submissions").glob("*.json"))


def test_cap_refuses_a_fourth_submission_on_the_same_utc_day(tmp_path: Path):
    candidate = _candidate()
    for i in range(DAILY_CAP):
        record_submission(candidate, f"kaggle-{i}", root=tmp_path, now=NOON + timedelta(hours=i))
    assert _files(tmp_path) == ["submission-001.json", "submission-002.json",
                                "submission-003.json"]
    with pytest.raises(SubmissionCapExceeded, match="00:00 UTC"):
        record_submission(candidate, "kaggle-4", root=tmp_path, now=NOON + timedelta(hours=11))
    assert len(_files(tmp_path)) == 3  # the refused submission wrote nothing
    assert slots_left(load_manifests(tmp_path), NOON) == 0
    with pytest.raises(SubmissionCapExceeded):
        assert_slot_available(load_manifests(tmp_path), NOON)


def test_cap_resets_at_utc_midnight(tmp_path: Path):
    candidate = _candidate()
    late = datetime(2026, 10, 24, 23, 59, 59, tzinfo=timezone.utc)
    for i in range(DAILY_CAP):
        record_submission(candidate, f"k{i}", root=tmp_path, now=late - timedelta(minutes=i))
    record = record_submission(candidate, "k-next", root=tmp_path, now=late + timedelta(seconds=1))
    assert record.candidate_id == "submission-004"
    assert submissions_per_utc_day(load_manifests(tmp_path)) == {
        late.date(): 3, (late + timedelta(seconds=1)).date(): 1}


def test_days_are_counted_in_utc_not_local_time(tmp_path: Path):
    # 21:00 in UTC-05:00 on Oct 24 is 02:00 UTC on Oct 25.
    evening = datetime(2026, 10, 24, 21, 0, tzinfo=timezone(timedelta(hours=-5)))
    assert str(utc_day(evening)) == "2026-10-25"
    candidate = _candidate()
    for i in range(DAILY_CAP):
        record_submission(candidate, f"k{i}", root=tmp_path, now=NOON)
    record_submission(candidate, "k-evening", root=tmp_path, now=evening)
    with pytest.raises(ValueError, match="no timezone"):
        utc_day("2026-10-24T12:00:00")


def test_submission_requires_g5_on_the_current_zip(tmp_path: Path):
    with pytest.raises(ManifestError, match="G5 not cleared"):
        record_submission(_candidate(g5=False), "k", root=tmp_path, now=NOON)
    moved = _candidate()
    moved.zip_sha256 = "cd" * 32  # the gates ran on a different zip
    with pytest.raises(ManifestError, match="G0 not cleared on the current zip"):
        record_submission(moved, "k", root=tmp_path, now=NOON)
    assert _files(tmp_path) == []


def test_waived_or_missing_gates_and_unmeasured_tasks_cannot_ship(tmp_path: Path):
    # A hand-edited manifest whose only record is a G5 WAIVED must not ship.
    forged = _candidate(g5=False)
    forged.gates = [GateRecord(gate="G5", status="WAIVED", timestamp_utc="",
                               zip_sha256=forged.zip_sha256, reason="trust me")]
    with pytest.raises(ManifestError) as err:
        record_submission(forged, "k", root=tmp_path, now=NOON)
    assert "G3 not cleared" in str(err.value) and "G5 is WAIVED, it must PASS" in str(err.value)
    waived_g3 = _candidate()
    waived_g3.gates[3].status = "WAIVED"
    with pytest.raises(ManifestError, match="G3 is WAIVED, it must PASS"):
        record_submission(waived_g3, "k", root=tmp_path, now=NOON)
    with pytest.raises(ManifestError, match="not every task is measured"):
        record_submission(_candidate(measured=False), "k", root=tmp_path, now=NOON)
    waived_g4 = _candidate()
    waived_g4.gates[4].status = "WAIVED"  # G4 may be waived (reference pipeline check)
    record_submission(waived_g4, "k-ok", root=tmp_path, now=NOON)
    assert _files(tmp_path) == ["submission-001.json"]


def test_submission_files_are_never_overwritten(tmp_path: Path):
    record_submission(_candidate(), "k1", root=tmp_path, now=NOON)
    # A second writer that computed the same number (no lock) fails instead of overwriting.
    from ledger.run_manifest import read_manifest
    from ledger.run_manifest import write_manifest as write

    first = tmp_path / "submissions" / "submission-001.json"
    clone = read_manifest(first)
    clone.kaggle_submission_id = "k-race"
    with pytest.raises(FileExistsError):
        write(clone, first, exclusive=True)
    assert read_manifest(first).kaggle_submission_id == "k1"
    rows = (tmp_path / "index.csv").read_text().splitlines()
    assert len(rows) == 2 and "submission-001" in rows[1]


def test_duplicate_kaggle_ids_are_refused(tmp_path: Path):
    candidate = _candidate()
    record_submission(candidate, "kaggle-1", root=tmp_path, now=NOON)
    with pytest.raises(ManifestError, match="already recorded"):
        record_submission(candidate, "kaggle-1", root=tmp_path, now=NOON)


def test_submission_manifest_points_at_its_candidate(tmp_path: Path):
    candidate = _candidate("cand-7")
    record = record_submission(candidate, "kaggle-9", root=tmp_path, now=NOON)
    assert record.kind == "submission"
    assert record.source_candidate_id == "cand-7"
    assert record.kaggle_submission_id == "kaggle-9"
    assert record.submitted_at_utc == NOON.isoformat()
    assert candidate.kind == "candidate" and candidate.kaggle_submission_id is None
    assert load_manifests(tmp_path)[0] == record


def test_table_best_per_task_and_archive(tmp_path: Path):
    write_manifest(_candidate("low", ratio=1.5), tmp_path / "candidates" / "low.json")
    write_manifest(_candidate("high", ratio=3.0), tmp_path / "candidates" / "high.json")
    write_manifest(_candidate("unmeasured", ratio=50.0, measured=False),
                   tmp_path / "candidates" / "unmeasured.json")
    record_submission(_candidate("low", ratio=1.5), "k1", root=tmp_path, now=NOON)
    manifests = load_manifests(tmp_path)
    assert best_per_task(manifests)["dqi"] == ("high", pytest.approx(3.0))
    assert best_geometric_mean(manifests) == ("high", pytest.approx(3.0))
    assert best_geometric_mean(manifests, exclude="high") == ("low", pytest.approx(1.5))
    table = render_markdown(manifests, now=NOON)
    assert "| high | candidate | 3.0000 | 3.0000 | 3.0000 | 3.0000 | yes | G5 |" in table
    assert "| unmeasured | candidate |" in table and "50.0000 | no |" in table
    assert "- 2026-10-24: 1" in table
    assert "slots left today (2026-10-24): 2" in table


def test_check_slot_cli(tmp_path: Path, capsys):
    assert main(["--root", str(tmp_path), "--check-slot"]) == 0
    candidate = _candidate()
    now = datetime.now(timezone.utc)
    for i in range(DAILY_CAP):
        record_submission(candidate, f"k{i}", root=tmp_path, now=now)
    assert main(["--root", str(tmp_path), "--check-slot"]) == 1
    assert "0 submission slot(s) left" in capsys.readouterr().out
