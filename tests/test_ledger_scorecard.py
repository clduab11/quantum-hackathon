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


# --- The cap is enforced before the upload (PRA-211) -----------------------------------------


import inspect  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402

from ledger.run_manifest import read_manifest, sha256_file  # noqa: E402
from ledger.scorecard import (  # noqa: E402
    Reservation,
    pending_reservations,
    reconcile_reservation,
    reserve_slot,
    submit,
)


def _shippable(tmp_path: Path, candidate_id: str = "cand"):
    """A fully gated candidate bound to a real zip file on disk."""
    zip_path = tmp_path / f"{candidate_id}.zip"
    zip_path.write_bytes(b"PK gated bytes " + candidate_id.encode())
    tasks = {t: TaskRecord(task=t, provenance=Provenance(licence="own"), cost=1.0,
                           baseline_cost=2.0, measured=True) for t in TASKS}
    manifest = create_manifest(candidate_id=candidate_id, tasks=tasks,
                               zip_sha256=sha256_file(zip_path))
    for gate in GATE_IDS:
        manifest.gates.append(GateRecord(gate=gate, status="PASS", timestamp_utc="",
                                         zip_sha256=manifest.zip_sha256))
    return manifest, zip_path


class _Spy:
    def __init__(self, ids=None, raises: Exception | None = None):
        self.calls: list[Path] = []
        self.ids = list(ids or [])
        self.raises = raises

    def __call__(self, zip_path: Path) -> str:
        self.calls.append(Path(zip_path))
        if self.raises is not None:
            raise self.raises
        return self.ids.pop(0) if self.ids else ""


def _reservation_files(root: Path) -> list[str]:
    return sorted(p.name for p in (root / "reservations").glob("*.json"))


def test_submit_reserves_then_uploads_then_records(tmp_path: Path):
    candidate, zip_path = _shippable(tmp_path)
    spy = _Spy(ids=["kaggle-1"])
    record = submit(candidate, zip_path, spy, root=tmp_path, now=NOON)
    assert spy.calls == [zip_path]
    assert record.candidate_id == "submission-001" and record.kaggle_submission_id == "kaggle-1"
    assert pending_reservations(tmp_path) == []
    (resolved,) = _reservation_files(tmp_path)
    assert resolved.startswith("2026-10-24-slot1-") and resolved.endswith(".recorded.json")
    assert slots_left(load_manifests(tmp_path), NOON, pending_reservations(tmp_path)) == 2


def test_fourth_upload_is_refused_before_the_uploader_runs(tmp_path: Path):
    """The test that fails if the pre-upload check is removed: the fourth call must raise before
    the uploader is invoked, and leave no reservation behind."""
    candidate, zip_path = _shippable(tmp_path)
    spy = _Spy(ids=["k1", "k2", "k3", "k4-must-never-be-used"])
    for i in range(DAILY_CAP):
        submit(candidate, zip_path, spy, root=tmp_path, now=NOON + timedelta(hours=i))
    assert len(spy.calls) == DAILY_CAP
    with pytest.raises(SubmissionCapExceeded, match="recorded or reserved on 2026-10-24"):
        submit(candidate, zip_path, spy, root=tmp_path, now=NOON + timedelta(hours=5))
    assert len(spy.calls) == DAILY_CAP  # the uploader did not run a fourth time
    assert spy.ids == ["k4-must-never-be-used"]
    assert pending_reservations(tmp_path) == []
    assert _files(tmp_path) == ["submission-001.json", "submission-002.json",
                                "submission-003.json"]
    # The next UTC day opens again, with the uploader called.
    submit(candidate, zip_path, spy, root=tmp_path, now=NOON + timedelta(days=1))
    assert len(spy.calls) == DAILY_CAP + 1


def test_a_failed_upload_keeps_its_reservation_and_counts_against_the_cap(tmp_path: Path):
    candidate, zip_path = _shippable(tmp_path)
    boom = _Spy(raises=RuntimeError("connection reset"))
    with pytest.raises(RuntimeError, match="connection reset"):
        submit(candidate, zip_path, boom, root=tmp_path, now=NOON)
    (held,) = pending_reservations(tmp_path)
    assert held.path.name == "2026-10-24-slot1.json" and held.slot == 1
    assert held.error == "upload raised RuntimeError: connection reset"
    assert held.candidate_id == "cand" and held.zip_sha256 == candidate.zip_sha256
    assert slots_left(load_manifests(tmp_path), NOON, pending_reservations(tmp_path)) == 2
    assert _files(tmp_path) == []  # nothing was recorded for the uncertain attempt

    # An uploader that returns no id is treated the same way.
    silent = _Spy(ids=[""])
    with pytest.raises(ManifestError, match="no Kaggle submission id"):
        submit(candidate, zip_path, silent, root=tmp_path, now=NOON)
    assert [r.slot for r in pending_reservations(tmp_path)] == [1, 2]

    # Two pending plus one recorded fill the day; the fourth attempt never uploads.
    ok = _Spy(ids=["k-ok", "k-never"])
    submit(candidate, zip_path, ok, root=tmp_path, now=NOON)
    with pytest.raises(SubmissionCapExceeded):
        submit(candidate, zip_path, ok, root=tmp_path, now=NOON)
    assert ok.calls == [zip_path]
    # The legacy direct record also sees the pending reservations.
    with pytest.raises(SubmissionCapExceeded):
        record_submission(candidate, "k-direct", root=tmp_path, now=NOON)

    # Reconciling the first failure (no Kaggle submission exists) frees exactly one slot.
    with pytest.raises(ValueError, match="written reason"):
        reconcile_reservation(tmp_path / "reservations" / "2026-10-24-slot1.json", reason="  ")
    closed = reconcile_reservation(tmp_path / "reservations" / "2026-10-24-slot1.json",
                                   reason="Kaggle shows no submission; socket reset before upload")
    assert closed.name.endswith(".failed.json")
    assert "socket reset" in closed.read_text()
    assert [r.slot for r in pending_reservations(tmp_path)] == [2]
    submit(candidate, zip_path, ok, root=tmp_path, now=NOON)
    assert ok.calls == [zip_path, zip_path]
    with pytest.raises(ManifestError, match="not pending"):
        reconcile_reservation(closed, reason="twice")


def test_a_recorded_reservation_cannot_be_reused(tmp_path: Path):
    candidate, zip_path = _shippable(tmp_path)
    held = reserve_slot(candidate, root=tmp_path, now=NOON)
    record_submission(candidate, "k1", root=tmp_path, now=NOON, reservation=held)
    assert not held.pending
    with pytest.raises(ManifestError, match="not pending"):
        record_submission(candidate, "k2", root=tmp_path, now=NOON, reservation=held)
    other, _ = _shippable(tmp_path, "other")
    held = reserve_slot(candidate, root=tmp_path, now=NOON)
    with pytest.raises(ManifestError, match="belongs to cand, not other"):
        record_submission(other, "k3", root=tmp_path, now=NOON, reservation=held)
    assert _files(tmp_path) == ["submission-001.json"]


def test_racing_reservers_never_exceed_the_cap(tmp_path: Path):
    """Eight reservers start together; exactly three hold a slot, the rest are refused."""
    candidate, _ = _shippable(tmp_path)
    outcomes: list[str] = []
    lock = threading.Lock()
    start = threading.Barrier(8)

    def reserve():
        start.wait()
        try:
            held = reserve_slot(candidate, root=tmp_path, now=NOON)
            result = f"slot{held.slot}"
        except SubmissionCapExceeded:
            result = "refused"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=reserve) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["refused"] * 5 + ["slot1", "slot2", "slot3"]
    assert _reservation_files(tmp_path) == ["2026-10-24-slot1.json", "2026-10-24-slot2.json",
                                            "2026-10-24-slot3.json"]
    with pytest.raises(SubmissionCapExceeded):
        assert_slot_available(load_manifests(tmp_path), NOON, pending_reservations(tmp_path))


def test_reservations_follow_the_utc_day_boundary(tmp_path: Path):
    candidate, zip_path = _shippable(tmp_path)
    late = datetime(2026, 10, 24, 23, 59, 59, tzinfo=timezone.utc)
    for _ in range(DAILY_CAP):
        reserve_slot(candidate, root=tmp_path, now=late)
    with pytest.raises(SubmissionCapExceeded):
        reserve_slot(candidate, root=tmp_path, now=late)
    # One second later the day has turned: three fresh slots, the old reservations still pending.
    midnight = late + timedelta(seconds=1)
    assert slots_left(load_manifests(tmp_path), midnight, pending_reservations(tmp_path)) == 3
    held = reserve_slot(candidate, root=tmp_path, now=midnight)
    assert held.path.name == "2026-10-25-slot1.json"
    # A reservation taken in UTC-05:00 evening lands on the UTC day, not the local one.
    evening = datetime(2026, 10, 25, 21, 0, tzinfo=timezone(timedelta(hours=-5)))
    assert reserve_slot(candidate, root=tmp_path, now=evening).utc_day == "2026-10-26"
    assert len(pending_reservations(tmp_path)) == 5


def test_the_cap_is_a_constant_no_caller_can_raise():
    assert DAILY_CAP == 3
    for fn in (submit, reserve_slot, record_submission, slots_left, assert_slot_available):
        assert "cap" not in inspect.signature(fn).parameters, fn.__name__


def test_submit_cli_runs_the_upload_command_only_while_a_slot_is_free(tmp_path: Path, capsys):
    candidate, zip_path = _shippable(tmp_path)
    manifest_path = tmp_path / "candidates" / "cand.json"
    write_manifest(candidate, manifest_path)
    marker = tmp_path / "uploads.log"
    # The fake uploader appends the zip path it was given and prints a Kaggle id last.
    command = (f"{sys.executable} -c \"import sys; open({str(marker)!r}, 'a').write(sys.argv[1] "
               f"+ chr(10)); print('starting'); print('kaggle-cli-' + str(len(open({str(marker)!r})"
               f".read().splitlines())))\"")
    for i in range(DAILY_CAP):
        assert main(["--root", str(tmp_path), "submit", "--candidate", str(manifest_path),
                     "--zip", str(zip_path), "--upload-command", command]) == 0, i
    assert marker.read_text().splitlines() == [str(zip_path)] * DAILY_CAP
    assert main(["--root", str(tmp_path), "submit", "--candidate", str(manifest_path),
                 "--zip", str(zip_path), "--upload-command", command]) == 1
    captured = capsys.readouterr()
    assert "REFUSED (cap)" in captured.err
    assert marker.read_text().splitlines() == [str(zip_path)] * DAILY_CAP  # no fourth upload
    assert main(["--root", str(tmp_path), "--check-slot"]) == 1
    assert "0 submission slot(s) left" in capsys.readouterr().out
    recorded = [read_manifest(p).kaggle_submission_id
                for p in sorted((tmp_path / "submissions").glob("*.json"))]
    assert recorded == ["kaggle-cli-1", "kaggle-cli-2", "kaggle-cli-3"]


def test_reserve_record_and_reconcile_cli(tmp_path: Path, capsys):
    candidate, zip_path = _shippable(tmp_path)
    manifest_path = tmp_path / "candidates" / "cand.json"
    write_manifest(candidate, manifest_path)
    assert main(["--root", str(tmp_path), "reserve", "--candidate", str(manifest_path)]) == 0
    out = capsys.readouterr().out
    assert "reserved slot 1 of 3" in out
    held = Reservation.from_path(pending_reservations(tmp_path)[0].path)
    assert main(["--root", str(tmp_path), "--check-slot"]) == 0
    assert "2 submission slot(s) left today (UTC); 1 pending reservation(s)" in capsys.readouterr().out
    assert main(["--root", str(tmp_path), "record", "--candidate", str(manifest_path),
                 "--kaggle-id", "k-sandbox", "--reservation", str(held.path)]) == 0
    assert pending_reservations(tmp_path) == [] and _files(tmp_path) == ["submission-001.json"]
    assert main(["--root", str(tmp_path), "reserve", "--candidate", str(manifest_path)]) == 0
    capsys.readouterr()
    pending = pending_reservations(tmp_path)[0].path
    assert main(["--root", str(tmp_path), "reconcile", "--reservation", str(pending),
                 "--failed", "--reason", "sandbox never started the upload"]) == 0
    assert "closed as failed" in capsys.readouterr().out
    # The CLI records at the real clock, so read the table for the real UTC day.
    today = utc_day(datetime.now(timezone.utc))
    table = render_markdown(load_manifests(tmp_path), reservations=pending_reservations(tmp_path))
    assert f"- pending reservations today ({today}): 0" in table
    assert f"slots left today ({today}): 2" in table
