"""Scorecard: every manifest in one table, and the Kaggle submission cap.

New for this repository (qrc-thresher has no scorecard module); it follows the run_manifest
pattern. The table shows the ratio per task, the geometric mean, the best measured ratio per
task and the number of Kaggle submissions per UTC day.

Submission rule (R6, AGENTS.md): only john-wick submits, hard cap 3 per UTC day, every
submission in the ledger. Since PRA-211 the cap is enforced *before* the upload, not after it:

1. `reserve_slot(candidate)` (CLI `reserve`) counts the UTC day's recorded submissions plus its
   pending reservations and raises `SubmissionCapExceeded` when they reach `DAILY_CAP`.
   Otherwise it creates `<root>/reservations/<day>-slot<k>.json` with an exclusive create
   (hard link), so two racing reservers can never hold the same slot and the fourth is refused.
2. The upload runs only inside `submit(candidate, zip_path, upload)` (CLI `submit
   --upload-command`): the reservation is taken first and the uploader is called second. A
   refused reservation means the uploader never runs.
3. `record_submission(candidate, kaggle_id, reservation=...)` writes `submission-NNN.json` and
   marks the reservation recorded. An upload that raised or returned no Kaggle id leaves its
   reservation pending, and a pending reservation keeps counting against the cap until an
   operator reconciles it (`reconcile --failed --reason ...`), because an uncertain attempt may
   have reached Kaggle.

`DAILY_CAP` is a module constant and no function takes a cap parameter: nothing a caller passes
can raise the limit. The ledger still cannot see an upload made outside `submit`/`reserve`; that
path is forbidden by AGENTS.md, not by code.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from ledger.run_manifest import (
    MANIFESTS_DIR,
    TASKS,
    ManifestError,
    RunManifest,
    _atomic_write_text,
    load_manifests,
    operator_id,
    read_manifest,
    sha256_file,
    utc_now,
    write_index,
    write_manifest,
)

DAILY_CAP = 3
RESERVATIONS_DIR = "reservations"
PENDING_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-slot(\d+)\.json$")

Uploader = Callable[[Path], str]


class SubmissionCapExceeded(RuntimeError):
    """The UTC day already has `DAILY_CAP` submissions recorded or reserved."""


def utc_day(timestamp: str | datetime) -> date:
    """The UTC calendar day of an ISO-8601 timestamp. Naive timestamps are rejected, because a
    local-time date can land a submission on the wrong Kaggle day."""
    moment = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp
    if moment.tzinfo is None:
        raise ValueError(f"timestamp {timestamp!r} has no timezone")
    return moment.astimezone(timezone.utc).date()


def submissions(manifests: list[RunManifest]) -> list[RunManifest]:
    return [m for m in manifests if m.kind == "submission"]


def submissions_per_utc_day(manifests: list[RunManifest]) -> dict[date, int]:
    counts: dict[date, int] = {}
    for m in submissions(manifests):
        day = utc_day(m.submitted_at_utc or m.timestamp_utc)
        counts[day] = counts.get(day, 0) + 1
    return dict(sorted(counts.items()))


# --- Reservations -----------------------------------------------------------------------------


@dataclass
class Reservation:
    """One held submission slot. While pending it is `<root>/reservations/<utc_day>-slot<k>.json`;
    once resolved it is renamed `<utc_day>-slot<k>-<id>.recorded.json` or `.failed.json` and no
    longer counts."""

    path: Path
    reservation_id: str
    candidate_id: str
    zip_sha256: str | None
    reserved_at_utc: str
    utc_day: str
    slot: int
    operator: str
    error: str = ""

    def dumps(self, **extra: object) -> str:
        data = {k: v for k, v in asdict(self).items() if k != "path"}
        data.update(extra)
        return json.dumps(data, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_path(cls, path: Path) -> Reservation:
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        fields = {k: data[k] for k in ("reservation_id", "candidate_id", "zip_sha256",
                                        "reserved_at_utc", "utc_day", "slot", "operator")}
        return cls(path=path, error=data.get("error", ""), **fields)

    @property
    def pending(self) -> bool:
        return self.path.is_file() and PENDING_NAME.match(self.path.name) is not None


def reservations_dir(root: Path = MANIFESTS_DIR) -> Path:
    return Path(root) / RESERVATIONS_DIR


def pending_reservations(root: Path = MANIFESTS_DIR) -> list[Reservation]:
    """Every pending reservation under `root`, oldest slot first."""
    directory = reservations_dir(root)
    if not directory.is_dir():
        return []
    return [Reservation.from_path(p) for p in sorted(directory.iterdir())
            if p.is_file() and PENDING_NAME.match(p.name)]


def used_slots(manifests: list[RunManifest], day: date,
               reservations: Sequence[Reservation] = ()) -> int:
    """Recorded submissions plus pending reservations on `day` (UTC)."""
    recorded = submissions_per_utc_day(manifests).get(day, 0)
    pending = sum(1 for r in reservations if r.utc_day == day.isoformat())
    return recorded + pending


def slots_left(manifests: list[RunManifest], now: datetime | None = None,
               reservations: Sequence[Reservation] = ()) -> int:
    now = now or datetime.now(timezone.utc)
    return max(0, DAILY_CAP - used_slots(manifests, utc_day(now), reservations))


def _cap_message(day: date) -> str:
    return (f"{DAILY_CAP} submissions already recorded or reserved on {day} (UTC); next slot "
            "opens at 00:00 UTC")


def assert_slot_available(manifests: list[RunManifest], now: datetime | None = None,
                          reservations: Sequence[Reservation] = ()) -> None:
    now = now or datetime.now(timezone.utc)
    if slots_left(manifests, now, reservations) == 0:
        raise SubmissionCapExceeded(_cap_message(utc_day(now)))


def _check_candidate(candidate: RunManifest) -> None:
    if candidate.kind != "candidate":
        raise ManifestError(f"{candidate.candidate_id} is a {candidate.kind}, not a candidate")
    problems = candidate.shipping_problems()
    if problems:
        raise ManifestError(f"{candidate.candidate_id} may not be submitted: "
                            + "; ".join(problems))


def reserve_slot(candidate: RunManifest, *, root: Path = MANIFESTS_DIR,
                 now: datetime | None = None) -> Reservation:
    """Hold the next free slot of the current UTC day for `candidate`, before any upload.

    Raises `SubmissionCapExceeded` (and writes nothing) when the day's recorded submissions plus
    pending reservations already reach `DAILY_CAP`. The slot file is created exclusively; a
    racing reserver that loses the race recounts and either takes the next slot or is refused.
    """
    _check_candidate(candidate)
    now = now or datetime.now(timezone.utc)
    day = utc_day(now)
    directory = reservations_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    for _attempt in range(DAILY_CAP + 1):
        used = used_slots(load_manifests(root), day, pending_reservations(root))
        if used >= DAILY_CAP:
            raise SubmissionCapExceeded(_cap_message(day))
        reservation = Reservation(
            path=directory / f"{day.isoformat()}-slot{used + 1}.json",
            reservation_id=str(uuid4()),
            candidate_id=candidate.candidate_id,
            zip_sha256=candidate.zip_sha256,
            reserved_at_utc=now.astimezone(timezone.utc).isoformat(),
            utc_day=day.isoformat(),
            slot=used + 1,
            operator=operator_id(),
        )
        try:
            _atomic_write_text(reservation.path, reservation.dumps(), exclusive=True)
        except FileExistsError:
            continue  # a racing reserver took this slot: count again
        return reservation
    raise SubmissionCapExceeded(_cap_message(day))


def _annotate(reservation: Reservation, error: str) -> None:
    """Record why a pending reservation was not consumed; it stays pending."""
    reservation.error = error
    if reservation.pending:
        _atomic_write_text(reservation.path, reservation.dumps())


def _resolve(reservation: Reservation, outcome: str, **extra: object) -> Path:
    if not reservation.pending:
        raise ManifestError(f"reservation {reservation.path} is not pending")
    resolved = reservation.path.with_name(
        f"{reservation.utc_day}-slot{reservation.slot}-{reservation.reservation_id[:8]}"
        f".{outcome}.json")
    _atomic_write_text(resolved, reservation.dumps(outcome=outcome, resolved_at_utc=utc_now(),
                                                   **extra), exclusive=True)
    reservation.path.unlink()
    reservation.path = resolved
    return resolved


def reconcile_reservation(path: Path, *, reason: str) -> Path:
    """Close a pending reservation whose upload is known to have failed (no Kaggle submission
    exists for it), freeing its slot. Needs a written reason; the file is kept as `.failed.json`.
    A reservation whose upload did reach Kaggle is closed with `record_submission` instead."""
    if not reason.strip():
        raise ValueError("reconciling a reservation needs a written reason")
    reservation = Reservation.from_path(path)
    return _resolve(reservation, "failed", reason=reason.strip())


# --- Recording and submitting -----------------------------------------------------------------


def record_submission(
    candidate: RunManifest,
    kaggle_submission_id: str,
    *,
    root: Path = MANIFESTS_DIR,
    now: datetime | None = None,
    index_csv: Path | None = None,
    reservation: Reservation | None = None,
) -> RunManifest:
    """Write the `submission-NNN` manifest for a fully gated candidate.

    Refuses (and writes nothing) if the candidate may not ship (`shipping_problems`: every gate
    cleared on the current zip, G0/G3/G5 real PASS, every task measured) or if the Kaggle id is
    already recorded. With `reservation` (the `submit` path) the slot was checked when it was
    reserved, so the record is written and the reservation is marked recorded: a submission that
    reached Kaggle is never left out of the ledger. Without one (records made outside `submit`)
    the UTC day must still have a free slot, counting pending reservations. The file is created
    exclusively, so a concurrent writer fails instead of overwriting. The derived index
    `index_csv` (default `<root>/index.csv`, not committed) is then rewritten from `root`.
    """
    _check_candidate(candidate)
    if not kaggle_submission_id:
        raise ManifestError("kaggle_submission_id is empty")
    now = now or datetime.now(timezone.utc)
    existing = load_manifests(root)
    previous = submissions(existing)
    if any(m.kaggle_submission_id == kaggle_submission_id for m in previous):
        raise ManifestError(f"Kaggle submission {kaggle_submission_id} is already recorded")
    if reservation is None:
        assert_slot_available(existing, now, pending_reservations(root))
    else:
        if not reservation.pending:
            raise ManifestError(f"reservation {reservation.path} is not pending")
        if reservation.candidate_id != candidate.candidate_id:
            raise ManifestError(f"reservation {reservation.path.name} belongs to "
                                f"{reservation.candidate_id}, not {candidate.candidate_id}")

    record = copy.deepcopy(candidate)
    record.manifest_id = str(uuid4())
    record.kind = "submission"
    record.candidate_id = f"submission-{len(previous) + 1:03d}"
    record.source_candidate_id = candidate.candidate_id
    record.operator = operator_id()
    record.timestamp_utc = now.astimezone(timezone.utc).isoformat()
    record.submitted_at_utc = record.timestamp_utc
    record.kaggle_submission_id = kaggle_submission_id
    write_manifest(record, Path(root) / "submissions" / f"{record.candidate_id}.json",
                   exclusive=True)
    if reservation is not None:
        _resolve(reservation, "recorded", kaggle_submission_id=kaggle_submission_id,
                 submission_id=record.candidate_id)
    write_index(Path(root), index_csv)
    return record


def submit(
    candidate: RunManifest,
    zip_path: Path,
    upload: Uploader,
    *,
    root: Path = MANIFESTS_DIR,
    now: datetime | None = None,
    index_csv: Path | None = None,
) -> RunManifest:
    """The only sanctioned upload path: reserve a slot, then upload, then record.

    `upload(zip_path)` performs the Kaggle upload and returns the Kaggle submission id. It is
    called only after `reserve_slot` succeeded, so a fourth upload on a UTC day is refused before
    anything leaves the machine. If it raises or returns no id, the reservation stays pending
    (with the error written into it) and keeps its slot until reconciled.
    """
    _check_candidate(candidate)
    zip_path = Path(zip_path)
    actual = sha256_file(zip_path)
    if actual != candidate.zip_sha256:
        raise ManifestError(f"{zip_path} has SHA-256 {actual[:12]}, the gated zip is "
                            f"{(candidate.zip_sha256 or '')[:12]}")
    reservation = reserve_slot(candidate, root=root, now=now)
    try:
        kaggle_id = upload(zip_path)
    except BaseException as exc:
        _annotate(reservation, f"upload raised {type(exc).__name__}: {exc}")
        raise
    kaggle_id = (kaggle_id or "").strip() if isinstance(kaggle_id, str) else ""
    if not kaggle_id:
        _annotate(reservation, "uploader returned no Kaggle submission id")
        raise ManifestError(f"uploader returned no Kaggle submission id; reservation "
                            f"{reservation.path.name} stays pending until reconciled")
    return record_submission(candidate, kaggle_id, root=root, now=now, index_csv=index_csv,
                             reservation=reservation)


def command_uploader(argv: Sequence[str]) -> Uploader:
    """An uploader that runs `argv` with the zip path appended and takes the last non-empty
    stdout line as the Kaggle submission id. A non-zero exit raises CalledProcessError."""
    def upload(zip_path: Path) -> str:
        proc = subprocess.run([*argv, str(zip_path)], capture_output=True, text=True, check=True)
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        return lines[-1] if lines else ""
    return upload


# --- Table ------------------------------------------------------------------------------------


@dataclass
class ScoreRow:
    candidate_id: str
    kind: str
    timestamp_utc: str
    ratios: dict[str, float | None]
    geometric_mean: float | None
    measured: bool
    last_gate: str
    kaggle_submission_id: str | None


def build_rows(manifests: list[RunManifest]) -> list[ScoreRow]:
    rows = []
    for m in manifests:
        rows.append(
            ScoreRow(
                candidate_id=m.candidate_id,
                kind=m.kind,
                timestamp_utc=m.timestamp_utc,
                ratios={t: (m.tasks[t].ratio if t in m.tasks else None) for t in TASKS},
                geometric_mean=m.geometric_mean,
                measured=m.is_measured(),
                last_gate=m.last_cleared_gate(),
                kaggle_submission_id=m.kaggle_submission_id,
            )
        )
    return rows


def best_per_task(manifests: list[RunManifest]) -> dict[str, tuple[str, float] | None]:
    """Best measured ratio per task across candidates. Unmeasured numbers never count."""
    best: dict[str, tuple[str, float] | None] = {t: None for t in TASKS}
    for m in manifests:
        if m.kind != "candidate":
            continue
        for task in TASKS:
            record = m.tasks.get(task)
            if record is None or not record.measured or record.ratio is None:
                continue
            current = best[task]
            if current is None or record.ratio > current[1]:
                best[task] = (m.candidate_id, record.ratio)
    return best


def best_geometric_mean(
    manifests: list[RunManifest], exclude: str | None = None
) -> tuple[str, float] | None:
    """Best fully measured candidate geometric mean (the archive G4 must beat)."""
    best = None
    for m in manifests:
        if m.kind != "candidate" or m.candidate_id == exclude or not m.is_measured():
            continue
        gm = m.geometric_mean
        if gm is not None and (best is None or gm > best[1]):
            best = (m.candidate_id, gm)
    return best


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.4f}"


def render_markdown(manifests: list[RunManifest], now: datetime | None = None,
                    reservations: Sequence[Reservation] = ()) -> str:
    now = now or datetime.now(timezone.utc)
    lines = [
        "| candidate | kind | invsqrt | dqi | dfthcsos | geo. mean | measured | last gate | Kaggle id |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for row in build_rows(manifests):
        lines.append(
            f"| {row.candidate_id} | {row.kind} | "
            + " | ".join(_fmt(row.ratios[t]) for t in TASKS)
            + f" | {_fmt(row.geometric_mean)} | {'yes' if row.measured else 'no'} | "
            f"{row.last_gate or '—'} | {row.kaggle_submission_id or '—'} |"
        )
    lines += ["", "Best measured ratio per task:", ""]
    for task, best in best_per_task(manifests).items():
        lines.append(f"- {task}: " + ("—" if best is None else f"{best[1]:.4f} ({best[0]})"))
    lines += ["", f"Kaggle submissions per UTC day (cap {DAILY_CAP}):", ""]
    per_day = submissions_per_utc_day(manifests)
    lines += [f"- {day}: {count}" for day, count in per_day.items()] or ["- none"]
    today = utc_day(now)
    pending = [r for r in reservations if r.utc_day == today.isoformat()]
    lines.append(f"- pending reservations today ({today}): {len(pending)}"
                 + (" (" + ", ".join(r.path.name for r in pending) + ")" if pending else ""))
    lines.append(f"- slots left today ({today}): {slots_left(manifests, now, reservations)}")
    return "\n".join(lines) + "\n"


# --- CLI --------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=MANIFESTS_DIR)
    parser.add_argument("--check-slot", action="store_true",
                        help="exit 1 if today's UTC submission cap is used up (recorded plus "
                             "pending reservations)")
    sub = parser.add_subparsers(dest="command")
    reserve = sub.add_parser("reserve", help="hold today's next slot before an upload; exit 1 "
                                             "and write nothing when the cap is used up")
    reserve.add_argument("--candidate", type=Path, required=True, help="candidate manifest")
    submit_cmd = sub.add_parser(
        "submit", help="reserve a slot, run the upload command with the zip path appended, "
                       "then record the Kaggle id it prints on its last stdout line")
    submit_cmd.add_argument("--candidate", type=Path, required=True)
    submit_cmd.add_argument("--zip", type=Path, required=True)
    submit_cmd.add_argument("--upload-command", required=True,
                            help="shell words of the uploader, e.g. a Kaggle CLI wrapper")
    record = sub.add_parser("record", help="record a submission made under a reservation "
                                           "(for example through the Composio sandbox route)")
    record.add_argument("--candidate", type=Path, required=True)
    record.add_argument("--kaggle-id", required=True)
    record.add_argument("--reservation", type=Path, required=True)
    reconcile = sub.add_parser("reconcile", help="close a pending reservation whose upload is "
                                                 "known to have failed; frees its slot")
    reconcile.add_argument("--reservation", type=Path, required=True)
    reconcile.add_argument("--failed", action="store_true", required=True,
                           help="confirm no Kaggle submission exists for this reservation")
    reconcile.add_argument("--reason", required=True)
    args = parser.parse_args(argv)

    manifests = load_manifests(args.root)
    reservations = pending_reservations(args.root)
    if args.command is None:
        if args.check_slot:
            left = slots_left(manifests, reservations=reservations)
            print(f"{left} submission slot(s) left today (UTC); "
                  f"{len(reservations)} pending reservation(s)")
            return 0 if left else 1
        sys.stdout.write(render_markdown(manifests, reservations=reservations))
        return 0
    try:
        if args.command == "reserve":
            held = reserve_slot(read_manifest(args.candidate), root=args.root)
            print(f"reserved slot {held.slot} of {DAILY_CAP} for {held.utc_day} (UTC): {held.path}")
        elif args.command == "submit":
            recorded = submit(read_manifest(args.candidate), args.zip,
                              command_uploader(shlex.split(args.upload_command)), root=args.root)
            print(f"recorded {recorded.candidate_id} (Kaggle {recorded.kaggle_submission_id})")
        elif args.command == "record":
            recorded = record_submission(read_manifest(args.candidate), args.kaggle_id,
                                         root=args.root,
                                         reservation=Reservation.from_path(args.reservation))
            print(f"recorded {recorded.candidate_id} (Kaggle {recorded.kaggle_submission_id})")
        elif args.command == "reconcile":
            print(f"closed as failed: {reconcile_reservation(args.reservation, reason=args.reason)}")
    except SubmissionCapExceeded as exc:
        print(f"REFUSED (cap): {exc}", file=sys.stderr)
        return 1
    except (ManifestError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        if args.command == "submit":
            print("the reservation stays pending; record it with `record --kaggle-id` if the "
                  "upload reached Kaggle, else `reconcile --failed --reason ...`",
                  file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
