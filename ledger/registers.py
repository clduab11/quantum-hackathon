"""Merge-safe registers: decisions, third-party notices and the manifest index (PRA-210).

Three registers used to be single files that every candidate branch appended to, so any two
branches cut from the same `main` conflicted after the first squash merge. Each register is now
one file per entry, so two branches only touch the same file when they really change the same
entry, and the whole register is assembled from those files when it is read.

- Decisions: `docs/DECISIONS.md` keeps its rows up to D-PRA206-01 unchanged and takes no new
  rows. Each new decision is `docs/decisions/<id>.md`, holding one table row in the same format.
  The register is the closed rows in file order, then the files by date and id.
- Notices: `NOTICE` holds the project line and points at `notices/`. Each third-party entry is a
  file `notices/NN-<area>.txt` of `- ` bullets, one file per task area, so the invsqrt and dqi
  parents never share a file. The full notice is the NOTICE head plus the files in name order.
- Index: `ledger/manifests/index.csv` is derived from the manifests and is not committed.
  `ledger/manifests/index-legacy.csv` keeps the rows appended before PRA-210, byte for byte.

`python -m ledger.registers check` validates all three (the merge gate runs it on every merged
queue); `decisions` and `notice` print the assembled registers; `index` rewrites index.csv.
Standard library only: the status page build (vercel.json) installs nothing else.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CLOSED_DECISIONS = Path("docs") / "DECISIONS.md"
DECISIONS_DIR = Path("docs") / "decisions"
NOTICE = Path("NOTICE")
NOTICES_DIR = Path("notices")
LEGACY_INDEX = Path("ledger") / "manifests" / "index-legacy.csv"

# SHA-256 of the closed register's table rows ("| 20..." lines, joined with "\n") and of the
# legacy index file. A branch that appends to either fails `check` and is told where the entry
# goes instead. Nothing may change these files' rows: they are the register's history.
CLOSED_DECISION_ROWS_SHA256 = "babd67109ef5e86bdefa2f21e26879a9a3ec4cd018ccfba80756f80ba2e50d7b"
CLOSED_DECISION_ROW_COUNT = 56
LEGACY_INDEX_SHA256 = "de50402e697fb355c6006c1df1e611d06525ec5967c00c0cfe097c9537737e94"

NOTICE_HEADING = "Third-party material in this tree:"
DECISION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NOTICE_NAME = re.compile(r"^\d{2}-[a-z0-9][a-z0-9-]*\.txt$")


@dataclass(frozen=True)
class DecisionRow:
    date: str
    id: str
    line: str
    source: str


def split_row(line: str) -> list[str]:
    """The cells of one register table row; escaped pipes (`\\|`) stay inside a cell."""
    line = line.strip()
    if not (line.startswith("|") and line.endswith("|")):
        return []
    return [c.strip() for c in re.split(r"(?<!\\)\|", line[1:-1])]


def _natural(text: str) -> list[object]:
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", text)]


def closed_rows(root: Path = REPO_ROOT) -> list[str]:
    text = (root / CLOSED_DECISIONS).read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.startswith("| 20")]


def decision_rows(root: Path = REPO_ROOT) -> list[DecisionRow]:
    """Every register row: the closed rows in file order, then one row per decision file, by
    date and then id (numbers compared as numbers). Raises ValueError on a malformed file."""
    rows = []
    for line in closed_rows(root):
        cells = split_row(line)
        rows.append(DecisionRow(cells[0], cells[1], line, str(CLOSED_DECISIONS)))
    fragments = []
    for path in sorted((root / DECISIONS_DIR).glob("*.md")):
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        rel = f"{DECISIONS_DIR}/{path.name}"
        if len(lines) != 1:
            raise ValueError(f"{rel}: holds {len(lines)} non-blank lines; one table row expected")
        cells = split_row(lines[0])
        if len(cells) != 5:
            raise ValueError(f"{rel}: not a five-cell register row "
                             "(| date | id | decision | evidence | status |)")
        date, ident = cells[0], cells[1]
        if not DATE.match(date):
            raise ValueError(f"{rel}: date {date!r} is not YYYY-MM-DD")
        if ident != path.stem or not DECISION_ID.match(ident):
            raise ValueError(f"{rel}: row id {ident!r} must equal the file name stem")
        fragments.append(DecisionRow(date, ident, lines[0].strip(), rel))
    fragments.sort(key=lambda r: (r.date, _natural(r.id)))
    return rows + fragments


def decisions_text(root: Path = REPO_ROOT) -> str:
    """The whole register as one markdown table (what `parse_decisions` reads)."""
    head = ["# Decisions register (assembled)", "",
            "| date | id | decision | evidence | status |", "| --- | --- | --- | --- | --- |"]
    return "\n".join(head + [r.line for r in decision_rows(root)]) + "\n"


def notice_files(root: Path = REPO_ROOT) -> list[Path]:
    return sorted((root / NOTICES_DIR).glob("*.txt"))


def notice_text(root: Path = REPO_ROOT) -> str:
    """The full NOTICE: the project paragraph of `NOTICE`, the heading, then every bullet of
    `notices/*.txt` in file-name order."""
    head = (root / NOTICE).read_text(encoding="utf-8").split("\n\n", 1)[0]
    body = "".join(p.read_text(encoding="utf-8") for p in notice_files(root))
    return f"{head}\n\n{NOTICE_HEADING}\n\n{body}"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def problems(root: Path = REPO_ROOT) -> list[str]:
    """Every rule the registers break, as one sentence each; empty when they are correct."""
    found: list[str] = []

    # Decisions.
    closed = closed_rows(root)
    if len(closed) != CLOSED_DECISION_ROW_COUNT or (
            _sha256_text("\n".join(closed)) != CLOSED_DECISION_ROWS_SHA256):
        found.append(f"{CLOSED_DECISIONS} rows changed ({len(closed)} rows; "
                     f"{CLOSED_DECISION_ROW_COUNT} expected). That file is closed: add a new "
                     f"decision as {DECISIONS_DIR}/<id>.md and supersede old rows from there.")
    try:
        rows = decision_rows(root)
    except ValueError as exc:
        found.append(str(exc))
        rows = []
    seen: dict[str, str] = {}
    for row in rows:
        if row.id in seen:
            found.append(f"decision id {row.id} appears twice ({seen[row.id]}, {row.source})")
        seen.setdefault(row.id, row.source)

    # Notices.
    notice = (root / NOTICE).read_text(encoding="utf-8")
    if any(line.startswith("- ") for line in notice.splitlines()):
        found.append(f"{NOTICE} holds a third-party bullet; it belongs in {NOTICES_DIR}/NN-<area>.txt")
    bullets: dict[str, str] = {}
    for path in notice_files(root):
        rel = f"{NOTICES_DIR}/{path.name}"
        text = path.read_text(encoding="utf-8")
        if not NOTICE_NAME.match(path.name):
            found.append(f"{rel}: name must be NN-<area>.txt (two digits, lower-case area)")
        if not text.strip() or not text.endswith("\n"):
            found.append(f"{rel}: must be non-empty and end with a newline")
        for line in text.splitlines():
            if not line.startswith("- "):
                found.append(f"{rel}: every line must be one '- ' bullet")
                break
            if line in bullets:
                found.append(f"{rel}: bullet repeated from {bullets[line]}")
            bullets.setdefault(line, rel)
    if not bullets:
        found.append(f"{NOTICES_DIR}/ holds no third-party notices")

    # Index.
    legacy = root / LEGACY_INDEX
    if not legacy.exists() or hashlib.sha256(legacy.read_bytes()).hexdigest() != LEGACY_INDEX_SHA256:
        found.append(f"{LEGACY_INDEX} changed or is missing. It is the frozen pre-PRA-210 log; "
                     "index.csv is derived (python -m ledger.registers index) and not committed.")
    gitignore = root / ".gitignore"
    ignored = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    if "ledger/manifests/index.csv" not in ignored:
        found.append(".gitignore must list ledger/manifests/index.csv (it is derived)")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("check", "decisions", "notice", "index"))
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root")
    args = parser.parse_args(argv)
    if args.command == "check":
        found = problems(args.root)
        for line in found:
            print(f"FAIL {line}")
        if not found:
            rows = decision_rows(args.root)
            print(f"OK registers: {len(rows)} decisions, "
                  f"{len(notice_files(args.root))} notice files, legacy index unchanged")
        return 1 if found else 0
    if args.command == "decisions":
        sys.stdout.write(decisions_text(args.root))
    elif args.command == "notice":
        sys.stdout.write(notice_text(args.root))
    else:
        from ledger.run_manifest import write_index

        print(write_index(args.root / "ledger" / "manifests"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
