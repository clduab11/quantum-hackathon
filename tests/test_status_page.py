from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest
import yaml

from ledger.run_manifest import (
    GATE_IDS,
    TASKS,
    GateRecord,
    Provenance,
    TaskRecord,
    create_manifest,
    load_manifests,
)
from ledger.scorecard import submissions
from ledger.gates.runner import load_config
from ledger.status_page import (
    STANDING_PATH,
    TRACKS_PATH,
    StandingError,
    TracksError,
    build,
    checks_sentence,
    featured_candidate,
    gate_cell,
    load_standing,
    load_tracks,
    parse_standing,
    parse_tracks,
    public_scores,
    render_page,
)

STANDING = yaml.safe_load(STANDING_PATH.read_text(encoding="utf-8"))
TRACKS = yaml.safe_load(TRACKS_PATH.read_text(encoding="utf-8"))


def _submission(candidate_id: str, submitted: str, *, gates: dict[str, str] | None = None):
    tasks = {t: TaskRecord(task=t, provenance=Provenance(licence="own"), cost=1.0,
                           baseline_cost=2.0, measured=True) for t in TASKS}
    m = create_manifest(candidate_id=candidate_id, tasks=tasks, zip_sha256="ab" * 32)
    m.kind, m.submitted_at_utc = "submission", submitted
    for gate, status in (gates or {g: "PASS" for g in GATE_IDS}).items():
        m.gates.append(GateRecord(gate=gate, status=status, timestamp_utc="",
                                  zip_sha256=m.zip_sha256))
    return m


def _gated(candidate_id: str, cleared: int, *, kind: str = "candidate",
           zip_sha256: str | None = None):
    """A manifest whose first `cleared` gates PASS; `zip_sha256` binds them to another zip."""
    tasks = {t: TaskRecord(task=t, provenance=Provenance(licence="own"), cost=1.0,
                           baseline_cost=2.0, measured=True) for t in TASKS}
    m = create_manifest(candidate_id=candidate_id, tasks=tasks, zip_sha256="ab" * 32)
    m.kind = kind
    for gate in GATE_IDS[:cleared]:
        m.gates.append(GateRecord(gate=gate, status="PASS", timestamp_utc="",
                                  zip_sha256=zip_sha256 or m.zip_sha256))
    return m


def _standing(**changes):
    data = copy.deepcopy(STANDING)
    for path, value in changes.items():
        *parents, key = path.split("__")
        node = data
        for p in parents:
            node = node[p]
        node[key] = value
    return parse_standing(data)


def _text(page: str) -> str:
    """The words a reader sees: no tags, no style sheet."""
    page = re.sub(r"<style>.*?</style>", "", page, flags=re.DOTALL)
    return re.sub(r" ([.,)])", r"\1", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page)))


def test_committed_standing_parses_and_names_every_submission():
    standing = load_standing()
    shipped = submissions(load_manifests())
    assert shipped, "the ledger has submissions"
    for m in shipped:
        assert standing.submission_notes.get(m.candidate_id), f"no note for {m.candidate_id}"
    assert set(standing.best_public) == set(TASKS)


@pytest.mark.parametrize("change", [
    {"schema": 2},
    {"leaderboard__rank": "585"},
    {"leaderboard__rank": True},
    {"leaderboard__read_at_utc": "yesterday"},
    {"best_public_per_task__dqi": None},
    {"notebook_url": "javascript:alert(1)"},
])
def test_malformed_standing_fails_the_build(change):
    with pytest.raises(StandingError):
        _standing(**change)


def test_page_reads_the_ledger_and_the_standing_file(tmp_path: Path):
    page = build(tmp_path / "public").read_text(encoding="utf-8")
    text = _text(page)
    assert "Our public score is 10.89339, rank 537 of 1130 teams on 26 October 2026." in text
    assert "The leader scores 23.35228." in text
    assert "(6th) scores 20.40926" in text
    assert "invsqrt 13.16 15.04 1.0" in text      # ours, best public, reference
    assert "dqi 23.56 23.66 1.0" in text
    assert "dfthcsos 4.15 4.09 1.0" in text      # latest scored upload (submission-005)
    assert text.count("waiting for Kaggle") == 1   # submission-006, until its score lands
    for score in ("1.00000", "2.40948", "5.68935", "6.77899", "10.89339"):
        assert score in text
    assert "20 January 2027" in text


def test_page_is_one_plain_screen(tmp_path: Path):
    page = build(tmp_path / "public").read_text(encoding="utf-8")
    text = _text(page)
    assert "<script" not in page                       # no JavaScript
    assert "fonts.googleapis.com" not in page          # one request, no web fonts
    assert page.count("<svg") == 1                     # the gate circuit, inline
    assert len(text.split()) < 1000
    for jargon in ("manifest", "salt", "merge gate", "PRA-", "D-PRA", "candidate", "zip",
                   "worktree", "proxy", "parent"):
        assert jargon not in text, jargon
    for heading in ("Where we stand", "What we are working on", "How each upload is checked",
                    "Our uploads", "Where every circuit comes from"):
        assert f">{heading}</h2>" in page, heading
    assert 'href="https://github.com/clduab11/quantum-hackathon"' in page
    assert "kaggle.com/competitions/google-verifiable-quantum-circuit-compilation" in page
    assert "/tree/main/docs/decisions" in page


def test_circuit_draws_the_latest_upload_from_the_ledger(tmp_path: Path):
    page = build(tmp_path / "public").read_text(encoding="utf-8")
    svg = page[page.index("<svg"):page.index("</svg>")]
    # submission-006: every gate passed on the uploaded zip; G1 and G2 are per circuit.
    assert '<g class="gate pass"><title>G0, all circuits: Passed</title>' in svg
    assert '<g class="gate pass"><title>G2 dqi: Passed</title>' in svg
    assert '<g class="gate pass"><title>G5, all circuits: Passed</title>' in svg
    assert "notrun" not in svg and "fail" not in svg
    for ratio in (">13.16</text>", ">26.30</text>", ">4.15</text>"):
        assert ratio in svg
    assert svg.count('class="inner"') == 3            # G0, G3, G5 are never waived
    text = _text(page)
    assert "It shows our latest upload, sent on 26 October 2026. For the latest upload, all six " \
           "of our automatic checks passed." in text


def test_circuit_shows_gate_failures_and_stale_records():
    m = _gated("submission-001", 1, kind="submission")
    m.submitted_at_utc = "2026-10-24T07:00:00+00:00"
    m.gates.append(GateRecord(
        gate="G1", status="FAIL", timestamp_utc="", zip_sha256=m.zip_sha256,
        details={"tasks": {"invsqrt": {"status": "PASS"}, "dqi": {"status": "FAIL: smoke"},
                           "dfthcsos": {"status": "PASS"}}}))
    m.gates.append(GateRecord(gate="G2", status="PASS", timestamp_utc="", zip_sha256="cd" * 32))
    page = render_page([m], _standing(), {})
    assert '<g class="gate fail"><title>G1 dqi: Failed (FAIL: smoke)</title>' in page
    assert ('<g class="gate stale"><title>G2 dqi: Ran on an earlier version (ran on an earlier '
            'version)</title>') in page
    assert '<g class="gate notrun"><title>G3, all circuits: Not run</title>' in page
    assert "invsqrt passed, dqi failed, dfthcsos passed" in page


def test_circuit_falls_back_to_the_furthest_candidate_before_any_upload():
    page = render_page([_gated("cand-a", 3), _gated("cand-b", 1)], _standing(), {})
    assert "Nothing is uploaded yet, so this shows the circuits furthest through our checks." \
        in page
    assert '<g class="gate pass"><title>G2 invsqrt: Passed</title>' in page
    assert '<g class="gate notrun"><title>G3, all circuits: Not run</title>' in page
    empty = render_page([], _standing(), {})
    assert "Nothing has entered our checks yet." in empty
    assert empty.count('<g class="gate notrun">') == 10   # 4 tall gates + 2 gates on 3 wires


def test_featured_candidate_prefers_the_furthest_gated_then_the_newest():
    assert featured_candidate([]) is None
    assert featured_candidate([_gated("submission-001", 6, kind="submission")]) is None
    older, newer = _gated("cand-a", 4), _gated("cand-b", 1)
    assert featured_candidate([older, newer]) is older
    older, newer = _gated("cand-a", 2), _gated("cand-b", 2)
    assert featured_candidate([older, newer]) is newer
    stale = _gated("cand-a", 6, zip_sha256="cd" * 32)  # every PASS is on an earlier zip
    current = _gated("cand-b", 1)
    assert featured_candidate([current, stale]) is current


def test_gate_cells_follow_the_ledger_rules():
    m = _gated("cand", 1)
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
    waived = _gated("cand", 0)
    waived.gates.append(GateRecord(gate="G1", status="WAIVED", timestamp_utc="",
                                   zip_sha256=waived.zip_sha256, reason="board waiver"))
    assert {gate_cell(waived, "G1", t).status for t in TASKS} == {"WAIVED"}


def test_committed_tracks_cover_the_four_programme_tracks():
    tracks = load_tracks()
    assert [t.id for t in tracks] == ["A", "B", "C", "D"]
    for t in tracks:
        assert t.figures, f"track {t.id} has no figures"


def test_shipped_track_figures_match_the_latest_upload():
    """'shipped' means 'in our latest upload': a new upload that changes a circuit's score must
    come with a tracks.yaml update, as a new upload must come with a note (PR #37)."""
    latest = max(submissions(load_manifests()), key=lambda m: m.submitted_at_utc)
    ours = {round(r.ratio, 2) for r in latest.tasks.values() if r.ratio is not None}
    for t in load_tracks():
        for f in t.figures:
            if f.state == "shipped":
                assert round(f.value, 2) in ours, f"track {t.id}: {f.label} {f.value} not shipped"


def _tracks(**changes):
    data = copy.deepcopy(TRACKS)
    figure = data["tracks"][0]["figures"][0]
    for key, value in changes.items():
        target, _, field = key.partition("__")
        node = {"doc": data, "track": data["tracks"][0], "figure": figure}[target]
        if value is _DELETE:
            node.pop(field)
        else:
            node[field] = value
    return parse_tracks(data)


_DELETE = object()


@pytest.mark.parametrize("change", [
    {"doc__schema": 2},
    {"doc__tracks": []},
    {"track__name": ""},
    {"track__aim": _DELETE},
    {"track__updated_at_utc": "today"},
    {"track__figures": "13.16"},
    {"track__id": "B"},                    # duplicate id
    {"figure__state": "done"},
    {"figure__value": None},               # shipped needs a measured value
    {"figure__value": "13.16"},
    {"figure__value": True},
    {"figure__value": 0},
    {"figure__state": "in work"},          # in work never carries a number
    {"figure__note": 3},
])
def test_malformed_tracks_fail_the_build(change):
    with pytest.raises(TracksError):
        _tracks(**change)


def test_tracks_render_escaped_and_in_work_has_no_number():
    tracks = parse_tracks({"schema": 1, "tracks": [{
        "id": "A", "name": "<b>Ship</b>", "aim": "Aim.", "updated_at_utc": "2026-10-26T06:00:00",
        "figures": [{"label": "x", "value": 2.5, "state": "verified", "note": "<i>n</i>"},
                    {"label": "Next", "state": "in work"}]}]})
    page = render_page([], _standing(), {}, tracks=tracks)
    assert "&lt;b&gt;Ship&lt;/b&gt;" in page and "&lt;i&gt;n&lt;/i&gt;" in page
    assert '<span class="fvalue">2.50×</span><span class="fstate verified">verified</span>' in page
    assert ('<li><span class="flabel">Next</span><span class="fstate inwork">in work</span></li>'
            in page)


def test_notebook_link_appears_only_when_set():
    shipped = [_submission("s-1", "2026-10-24T07:00:00+00:00")]
    without = render_page(shipped, _standing(), {"s-1": 1.0})
    with_link = render_page(shipped, _standing(notebook_url="https://www.kaggle.com/code/x/y"),
                            {"s-1": 1.0})
    assert "Our public notebook" not in without
    assert "A public Kaggle notebook that rebuilds the entry from source is on its way." \
        in _text(without)
    assert 'href="https://www.kaggle.com/code/x/y">Our public notebook' in with_link
    assert 'Our <a href="https://www.kaggle.com/code/x/y">public notebook</a> rebuilds' in with_link


def test_unscored_upload_waits_and_the_rank_says_when_it_is_stale():
    shipped = [_submission("s-1", "2026-10-24T07:00:00+00:00"),
               _submission("s-2", "2026-10-26T07:00:00+00:00")]
    text = _text(render_page(shipped, _standing(), {"s-1": 9.5}))
    assert "waiting for Kaggle" in text
    # The latest scored upload is s-1, whose score differs from the one the rank was read at.
    assert "Our public score is 9.50000, rank 537 of 1130 teams on 26 October 2026, before this " \
           "score came in." in text


def test_no_public_score_yet():
    text = _text(render_page([], _standing(), {}))
    assert "We have not had a public score back from Kaggle yet." in text
    assert "No uploads yet." in text


def test_checks_sentence_counts_only_the_uploaded_zip():
    assert checks_sentence(_submission("s", "2026-10-24T07:00:00+00:00")) == (
        "For the latest upload, all six of our automatic checks passed.")
    waived = _submission("s", "2026-10-24T07:00:00+00:00",
                         gates={"G0": "PASS", "G1": "PASS", "G2": "PASS", "G3": "PASS",
                                "G4": "WAIVED", "G5": "PASS"})
    assert checks_sentence(waived) == ("For the latest upload, five of our six automatic checks "
                                       "passed and one was waived, with the reason on record.")
    stale = _submission("s", "2026-10-24T07:00:00+00:00")
    stale.gates[-1].zip_sha256 = "cd" * 32
    assert checks_sentence(stale).startswith("For the latest upload, five of our six")


def test_page_escapes_standing_text():
    shipped = [_submission("s-1", "2026-10-24T07:00:00+00:00")]
    standing = _standing(submission_notes={"s-1": "<script>alert(1)</script>"})
    page = render_page(shipped, standing, {"s-1": 1.0})
    assert "<script>" not in page and "&lt;script&gt;" in page


def test_public_scores_read_the_evidence_files(tmp_path: Path):
    shipped = [_submission("s-1", "2026-10-24T07:00:00+00:00"),
               _submission("s-2", "2026-10-25T07:00:00+00:00")]
    (tmp_path / "s-1").mkdir()
    (tmp_path / "s-1" / "kaggle-public-score.json").write_text(
        json.dumps({"kaggle": {"publicScore": "2.40948"}}))
    assert public_scores(shipped, tmp_path) == {"s-1": 2.40948}
