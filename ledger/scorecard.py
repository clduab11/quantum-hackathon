"""Scorecard: every manifest in one table, and the Kaggle submission cap.

New for this repository (qrc-thresher has no scorecard module); it follows the run_manifest
pattern. The table shows the ratio per task, the geometric mean, the best measured ratio per
task and the number of Kaggle submissions per UTC day.

Submission rule (R6, AGENTS.md): only john-wick submits, hard cap 3 per UTC day, every
submission in the ledger. Procedure:

1. `python -m ledger.scorecard --check-slot` (or `assert_slot_available`) before submitting;
2. submit the queued zip to Kaggle;
3. `record_submission(...)` with the Kaggle submission id. It refuses a fourth submission on the
   same UTC day and refuses a candidate that fails the shipping rule (`shipping_problems`).
"""

from __future__ import annotations

import argparse
import copy
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from ledger.run_manifest import (
    MANIFESTS_DIR,
    TASKS,
    ManifestError,
    RunManifest,
    load_manifests,
    operator_id,
    write_index,
    write_manifest,
)

DAILY_CAP = 3


class SubmissionCapExceeded(RuntimeError):
    """The UTC day already has `DAILY_CAP` recorded submissions."""


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


def slots_left(
    manifests: list[RunManifest], now: datetime | None = None, cap: int = DAILY_CAP
) -> int:
    now = now or datetime.now(timezone.utc)
    return max(0, cap - submissions_per_utc_day(manifests).get(utc_day(now), 0))


def assert_slot_available(
    manifests: list[RunManifest], now: datetime | None = None, cap: int = DAILY_CAP
) -> None:
    now = now or datetime.now(timezone.utc)
    if slots_left(manifests, now, cap) == 0:
        raise SubmissionCapExceeded(
            f"{cap} submissions already recorded on {utc_day(now)} (UTC); next slot opens at "
            "00:00 UTC"
        )


def record_submission(
    candidate: RunManifest,
    kaggle_submission_id: str,
    *,
    root: Path = MANIFESTS_DIR,
    now: datetime | None = None,
    cap: int = DAILY_CAP,
    index_csv: Path | None = None,
) -> RunManifest:
    """Write the `submission-NNN` manifest for a fully gated candidate.

    Refuses (and writes nothing) if the candidate may not ship (`shipping_problems`: every gate
    cleared on the current zip, G0/G3/G5 real PASS, every task measured), if the Kaggle id is
    already recorded, or if the UTC day already holds `cap` submissions. The file is created
    exclusively, so a concurrent writer fails instead of overwriting. The derived index
    `index_csv` (default `<root>/index.csv`, not committed) is then rewritten from `root`.
    """
    if candidate.kind != "candidate":
        raise ManifestError(f"{candidate.candidate_id} is a {candidate.kind}, not a candidate")
    problems = candidate.shipping_problems()
    if problems:
        raise ManifestError(f"{candidate.candidate_id} may not be submitted: "
                            + "; ".join(problems))
    if not kaggle_submission_id:
        raise ManifestError("kaggle_submission_id is empty")
    now = now or datetime.now(timezone.utc)
    existing = load_manifests(root)
    previous = submissions(existing)
    if any(m.kaggle_submission_id == kaggle_submission_id for m in previous):
        raise ManifestError(f"Kaggle submission {kaggle_submission_id} is already recorded")
    assert_slot_available(existing, now, cap)

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
    write_index(Path(root), index_csv)
    return record


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


def render_markdown(manifests: list[RunManifest], now: datetime | None = None) -> str:
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
    lines += ["", "Kaggle submissions per UTC day (cap 3):", ""]
    per_day = submissions_per_utc_day(manifests)
    lines += [f"- {day}: {count}" for day, count in per_day.items()] or ["- none"]
    lines.append(f"- slots left today ({utc_day(now)}): {slots_left(manifests, now)}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=MANIFESTS_DIR)
    parser.add_argument("--check-slot", action="store_true",
                        help="exit 1 if today's UTC submission cap is used up")
    args = parser.parse_args(argv)
    manifests = load_manifests(args.root)
    if args.check_slot:
        left = slots_left(manifests)
        print(f"{left} submission slot(s) left today (UTC)")
        return 0 if left else 1
    sys.stdout.write(render_markdown(manifests))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
