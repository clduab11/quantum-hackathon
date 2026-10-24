from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from ledger.gates.runner import load_config
from ledger.run_manifest import GATE_IDS, TASKS, GateRecord, Provenance, TaskRecord, create_manifest
from ledger.status_page import (
    BuildInfo,
    Decision,
    build,
    deadline_sentence,
    featured_candidate,
    gate_cell,
    inline,
    parse_decisions,
    render_page,
    status_tone,
)

NOON = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
BUILD = BuildInfo(commit="ab" * 20, branch="main", built_at=NOON)


def _candidate(candidate_id: str = "cand"):
    tasks = {t: TaskRecord(task=t, provenance=Provenance(licence="own"), cost=1.0,
                           baseline_cost=2.0, measured=True) for t in TASKS}
    return create_manifest(candidate_id=candidate_id, tasks=tasks, zip_sha256="ab" * 32)


def _gated(candidate_id: str, cleared: int, *, kind: str = "candidate",
           zip_sha256: str | None = None):
    """A manifest whose first `cleared` gates PASS; `zip_sha256` binds them to another zip."""
    m = _candidate(candidate_id)
    m.kind = kind
    for gate in GATE_IDS[:cleared]:
        m.gates.append(GateRecord(gate=gate, status="PASS", timestamp_utc="",
                                  zip_sha256=zip_sha256 or m.zip_sha256))
    return m


def test_featured_candidate_is_none_without_candidates():
    assert featured_candidate([]) is None
    assert featured_candidate([_gated("submission-001", 6, kind="submission")]) is None


def test_featured_candidate_prefers_the_furthest_gated_over_the_newest():
    older, newer = _gated("cand-a", 4), _gated("cand-b", 1)
    assert featured_candidate([older, newer]) is older


def test_featured_candidate_breaks_ties_by_recency():
    older, newer = _gated("cand-a", 2), _gated("cand-b", 2)
    assert featured_candidate([older, newer]) is newer
    assert featured_candidate([_gated("cand-a", 0), _gated("cand-b", 0)]).candidate_id == "cand-b"


def test_featured_candidate_skips_submissions():
    candidate = _gated("cand-a", 1)
    shipped = _gated("submission-001", 6, kind="submission")
    assert featured_candidate([candidate, shipped]) is candidate


def test_featured_candidate_counts_only_gates_cleared_on_the_current_zip():
    stale = _gated("cand-a", 6, zip_sha256="cd" * 32)  # every PASS is on an earlier zip
    current = _gated("cand-b", 1)
    assert featured_candidate([current, stale]) is current


def test_page_traces_the_featured_candidate():
    page = render_page([_gated("cand-a", 3), _gated("cand-b", 1)], load_config(), [], BUILD)
    assert "Showing cand-a, last cleared gate G2." in page
    assert '<g class="gate pass"><title>G0, all tasks: Passed</title>' in page
    assert '<g class="gate notrun"><title>G3, all tasks: Not run</title>' in page


def test_gate_cells_follow_the_ledger_rules():
    m = _candidate()
    m.gates.append(GateRecord(gate="G0", status="PASS", timestamp_utc="", zip_sha256=m.zip_sha256))
    m.gates.append(GateRecord(
        gate="G1", status="FAIL", timestamp_utc="", zip_sha256=m.zip_sha256,
        details={"tasks": {"invsqrt": {"status": "PASS"}, "dqi": {"status": "FAIL: smoke"},
                           "dfthcsos": {"status": "PASS"}}}))
    m.gates.append(GateRecord(gate="G2", status="PASS", timestamp_utc="", zip_sha256="cd" * 32))
    assert gate_cell(m, "G0").status == "PASS"
    assert gate_cell(m, "G1", "invsqrt").status == "PASS"
    assert (gate_cell(m, "G1", "dqi").status, gate_cell(m, "G1", "dqi").reason) == (
        "FAIL", "FAIL: smoke")
    assert gate_cell(m, "G2", "dqi").status == "stale"  # bound to an earlier zip: not cleared
    assert gate_cell(m, "G3").status == "not run"
    assert gate_cell(None, "G0").status == "not run"


def test_waived_per_task_gate_stays_waived_on_every_wire():
    m = _candidate()
    m.gates.append(GateRecord(gate="G1", status="WAIVED", timestamp_utc="",
                              zip_sha256=m.zip_sha256, reason="board waiver"))
    assert {gate_cell(m, "G1", t).status for t in TASKS} == {"WAIVED"}


def test_register_rows_parse_with_escaped_pipes_and_skip_the_header():
    text = """# Decisions register

| date | id | decision | evidence | status |
| --- | --- | --- | --- | --- |
| 2026-10-24 | D-X-01 | Use `a \\| b` | PRA-1 | accepted |
| 2026-10-24 | D-X-02 | Revisit D-X-01 | review | unresolved |
"""
    rows = parse_decisions(text)
    assert [r.id for r in rows] == ["D-X-01", "D-X-02"]
    assert rows[0].decision == "Use `a | b`"


def test_committed_register_parses_completely():
    text = (Path(__file__).resolve().parent.parent / "docs" / "DECISIONS.md").read_text()
    rows = parse_decisions(text)
    table_lines = [ln for ln in text.splitlines() if ln.startswith("| 20")]
    assert len(rows) == len(table_lines) > 0


def test_status_tones():
    assert status_tone("unresolved") == "open"
    assert status_tone("independent lineage derivation unresolved") == "open"
    assert status_tone("implemented, review pending") == "pending"
    assert status_tone("accepted") == "settled"
    assert status_tone("corrected by subsequent test run") == "settled"
    assert status_tone("parked") == "neutral"


def test_inline_escapes_and_links_only_known_ids():
    out = inline("See D-X-01 and D-X-99 <b>`x<y`</b>", frozenset({"D-X-01"}))
    assert '<a href="#D-X-01">D-X-01</a>' in out
    assert "D-X-99" in out and 'href="#D-X-99"' not in out
    assert "&lt;b&gt;" in out and "<code>x&lt;y</code>" in out


def test_page_escapes_ledger_text():
    m = _candidate()
    m.kaggle_submission_id = "<script>alert(1)</script>"
    page = render_page([m], load_config(), [Decision("2026-10-24", "D-1", "<i>x</i>", "e", "accepted")],
                       BUILD)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;i&gt;x&lt;/i&gt;" in page


def test_deadline_sentence():
    assert deadline_sentence(date(2026, 10, 24)) == (
        "88 days to the final deadline, 20 January 2027.")
    assert deadline_sentence(date(2027, 1, 19)).startswith("1 day ")
    assert deadline_sentence(date(2027, 1, 20)) == "The final deadline is today, 20 January 2027."
    assert deadline_sentence(date(2027, 1, 21)).startswith("The final deadline passed")


def test_build_writes_the_page_from_the_committed_repo(tmp_path: Path):
    path = build(tmp_path / "public", manifests_root=tmp_path / "no-manifests", now=NOON)
    page = path.read_text(encoding="utf-8")
    assert path.name == "index.html"
    for gate in GATE_IDS:
        assert f">{gate}<" in page
    assert "No candidates in the ledger yet" in page
    assert 'id="D-PRA174-12"' in page
    assert "3</span> of 3 submissions left" in page
