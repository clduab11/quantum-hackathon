"""The merge-safe registers (PRA-210): decisions, notices and the derived manifest index."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest

from ledger import registers
from ledger.run_manifest import INDEX_FIELDNAMES, load_manifests, write_index

REPO_ROOT = Path(__file__).resolve().parent.parent

REGISTER_PATHS = ["NOTICE", "notices", "docs/DECISIONS.md", "docs/decisions", ".gitignore",
                  "ledger/manifests/index-legacy.csv"]


def copy_registers(dest: Path) -> Path:
    for rel in REGISTER_PATHS:
        src = REPO_ROOT / rel
        if src.is_dir():
            shutil.copytree(src, dest / rel)
        else:
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / rel)
    return dest


def row(ident: str, date: str = "2026-10-25") -> str:
    return f"| {date} | {ident} | test decision | test | accepted |\n"


def test_committed_registers_pass_the_check():
    assert registers.problems(REPO_ROOT) == []


def test_closed_register_rows_are_unchanged_and_take_no_new_rows(tmp_path: Path):
    root = copy_registers(tmp_path)
    closed = root / "docs" / "DECISIONS.md"
    closed.write_text(closed.read_text() + row("D-NEW-01"))
    found = registers.problems(root)
    assert any("closed" in p and "docs/decisions/<id>.md" in p for p in found), found


def test_a_decision_file_is_one_row_named_by_its_id(tmp_path: Path):
    root = copy_registers(tmp_path)
    (root / "docs" / "decisions" / "D-X-01.md").write_text(row("D-X-02"))
    assert any("must equal the file name stem" in p for p in registers.problems(root))
    (root / "docs" / "decisions" / "D-X-01.md").write_text(row("D-X-01") + row("D-X-01"))
    assert any("one table row expected" in p for p in registers.problems(root))


def test_a_repeated_decision_id_fails(tmp_path: Path):
    root = copy_registers(tmp_path)
    (root / "docs" / "decisions" / "R1.md").write_text(row("R1"))
    assert any("decision id R1 appears twice" in p for p in registers.problems(root))


def test_decision_files_follow_the_closed_rows_by_date_then_id(tmp_path: Path):
    root = copy_registers(tmp_path)
    for ident, date in [("D-Z-10", "2026-10-26"), ("D-Z-9", "2026-10-26"), ("D-Y-01", "2026-10-25")]:
        (root / "docs" / "decisions" / f"{ident}.md").write_text(row(ident, date))
    ids = [r.id for r in registers.decision_rows(root)]
    assert ids[0] == "D-001"
    assert ids[-3:] == ["D-Y-01", "D-Z-9", "D-Z-10"]
    assert registers.problems(root) == []


def test_whole_register_holds_each_ruling_once():
    from ledger.status_page import parse_decisions

    rows = parse_decisions(registers.decisions_text(REPO_ROOT))
    ids = [r.id for r in rows]
    assert len(rows) == len(registers.decision_rows(REPO_ROOT))
    for n in range(1, 13):
        assert ids.count(f"R{n}") == 1, f"R{n}"
    assert "D-PRA210-01" in ids and len(ids) == len(set(ids))


def test_third_party_bullets_live_in_notice_files(tmp_path: Path):
    root = copy_registers(tmp_path)
    notice = root / "NOTICE"
    notice.write_text(notice.read_text() + "\n- A new parent, Apache-2.0.\n")
    assert any("holds a third-party bullet" in p for p in registers.problems(root))


def test_notice_files_are_bullets_and_never_repeat(tmp_path: Path):
    root = copy_registers(tmp_path)
    first = (root / "notices" / "10-invsqrt.txt").read_text()
    (root / "notices" / "40-copy.txt").write_text(first)
    assert any("bullet repeated" in p for p in registers.problems(root))
    (root / "notices" / "40-copy.txt").write_text("not a bullet\n")
    assert any("every line must be one '- ' bullet" in p for p in registers.problems(root))


def test_assembled_notice_has_the_heading_and_every_entry():
    text = registers.notice_text(REPO_ROOT)
    assert text.startswith("quantum-hackathon")
    assert f"\n\n{registers.NOTICE_HEADING}\n\n- " in text
    for path in registers.notice_files(REPO_ROOT):
        assert path.read_text() in text


def test_legacy_index_is_frozen(tmp_path: Path):
    root = copy_registers(tmp_path)
    legacy = root / "ledger" / "manifests" / "index-legacy.csv"
    legacy.write_bytes(legacy.read_bytes() + b"x\r\n")
    assert any("index-legacy.csv changed" in p for p in registers.problems(root))


def test_derived_index_keeps_every_legacy_row_identity():
    """Every row appended before PRA-210 names a committed manifest, and the derived index
    reproduces its identity columns exactly. The columns that moved (gates, ratios) were the
    manifest's state when the row was written; that state stays in index-legacy.csv."""
    legacy = list(csv.DictReader((REPO_ROOT / "ledger/manifests/index-legacy.csv").open()))
    from ledger.run_manifest import index_row

    derived = {m.manifest_id: index_row(m) for m in load_manifests()}
    identity = ["manifest_id", "kind", "candidate_id", "parent_candidate_id", "timestamp_utc",
                "operator", "generator_commit", "salt_label", "zip_sha256"]
    assert legacy
    for old in legacy:
        assert {k: old[k] for k in identity} == {k: str(derived[old["manifest_id"]][k])
                                                for k in identity}


def test_write_index_derives_every_manifest(tmp_path: Path):
    shutil.copytree(REPO_ROOT / "ledger" / "manifests", tmp_path / "m")
    path = write_index(tmp_path / "m")
    rows = list(csv.DictReader(path.open()))
    assert list(rows[0]) == INDEX_FIELDNAMES
    assert [r["manifest_id"] for r in rows] == [m.manifest_id
                                               for m in load_manifests(tmp_path / "m")]
    before = path.read_bytes()
    write_index(tmp_path / "m")
    assert path.read_bytes() == before  # rewriting is idempotent


def test_check_command_reports(capsys: pytest.CaptureFixture[str]):
    assert registers.main(["check"]) == 0
    assert capsys.readouterr().out.startswith("OK registers:")
