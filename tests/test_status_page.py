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
from ledger.status_page import (
    STANDING_PATH,
    StandingError,
    build,
    checks_sentence,
    load_standing,
    parse_standing,
    public_scores,
    render_page,
)

STANDING = yaml.safe_load(STANDING_PATH.read_text(encoding="utf-8"))


def _submission(candidate_id: str, submitted: str, *, gates: dict[str, str] | None = None):
    tasks = {t: TaskRecord(task=t, provenance=Provenance(licence="own"), cost=1.0,
                           baseline_cost=2.0, measured=True) for t in TASKS}
    m = create_manifest(candidate_id=candidate_id, tasks=tasks, zip_sha256="ab" * 32)
    m.kind, m.submitted_at_utc = "submission", submitted
    for gate, status in (gates or {g: "PASS" for g in GATE_IDS}).items():
        m.gates.append(GateRecord(gate=gate, status=status, timestamp_utc="",
                                  zip_sha256=m.zip_sha256))
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
    assert "Our public score is 6.77899, rank 534 of 953 teams on 26 October 2026." in text
    assert "The leader scores 20.74782." in text
    assert "(6th) scores 18.66384" in text
    assert "invsqrt 13.16 15.04 1.0" in text      # ours, best public, reference
    assert "dqi 23.56 23.66 1.0" in text
    assert "dfthcsos 1.00 4.09 1.0" in text
    assert text.count("waiting for Kaggle") == 0
    for score in ("1.00000", "2.40948", "5.68935", "6.77899"):
        assert score in text
    assert "20 January 2027" in text


def test_page_is_one_plain_screen(tmp_path: Path):
    page = build(tmp_path / "public").read_text(encoding="utf-8")
    text = _text(page)
    assert "<script" not in page and "<svg" not in page
    assert "fonts.googleapis.com" not in page          # one request, no web fonts
    assert len(text.split()) < 450
    for jargon in ("manifest", "salt", "merge gate", "G3", "PRA-", "D-PRA", "candidate"):
        assert jargon not in text, jargon
    assert 'href="https://github.com/clduab11/quantum-hackathon"' in page
    assert "kaggle.com/competitions/google-verifiable-quantum-circuit-compilation" in page


def test_notebook_link_appears_only_when_set():
    shipped = [_submission("s-1", "2026-10-24T07:00:00+00:00")]
    without = render_page(shipped, _standing(), {"s-1": 1.0})
    with_link = render_page(shipped, _standing(notebook_url="https://www.kaggle.com/code/x/y"),
                            {"s-1": 1.0})
    assert "Our public notebook" not in without
    assert 'href="https://www.kaggle.com/code/x/y">Our public notebook' in with_link


def test_unscored_upload_waits_and_the_rank_says_when_it_is_stale():
    shipped = [_submission("s-1", "2026-10-24T07:00:00+00:00"),
               _submission("s-2", "2026-10-26T07:00:00+00:00")]
    text = _text(render_page(shipped, _standing(), {"s-1": 9.5}))
    assert "waiting for Kaggle" in text
    # The latest scored upload is s-1, whose score differs from the one the rank was read at.
    assert "Our public score is 9.50000, rank 534 of 953 teams on 26 October 2026, before this " \
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
