"""Status page: one plain-English screen on our Kaggle entry, as static HTML.

`python -m ledger.status_page --out public` writes `public/index.html`. Vercel runs it on every
push (`vercel.json`) and serves the folder as a static site. The reader is someone who knows
nothing about us (PRA-241) and, since PRA-252, the audience of the hackathon's final
presentation. The page says what the competition is, where we stand, what each of the four
programme tracks has verified, how our six automatic checks judged the latest upload (drawn as a
circuit), our uploads and how we prove where every circuit comes from.

Our numbers come from the ledger: the per-task ratios and gate states from the manifests, the
public scores from `ledger/evidence/<submission>/kaggle-public-score.json`. The leaderboard
numbers (rank, leader, prize line, best public per task) and the one-line upload notes come from
`ledger/standing.yaml`, which john-wick updates with every leaderboard snapshot; the track
figures come from `ledger/tracks.yaml`, which the engineers and john-wick update with every
verified number. Both are documented in `docs/ledger-schema.md`. A malformed manifest, gate
config, standing or tracks file fails the build instead of showing a wrong page. No JavaScript
and no web fonts: the page is the same for every reader and loads in one request.
"""

from __future__ import annotations

import argparse
import html
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

from ledger.gates.runner import DEFAULT_CONFIG, GateConfig, GateSpec, load_config
from ledger.run_manifest import (
    GATE_IDS,
    LEDGER_ROOT,
    MANIFESTS_DIR,
    REPO_ROOT,
    TASKS,
    UNWAIVABLE_GATES,
    RunManifest,
    load_manifests,
)
from ledger.scorecard import submissions

DEADLINE = date(2027, 1, 20)  # final Kaggle deadline (README)
REPO_URL = "https://github.com/clduab11/quantum-hackathon"
KAGGLE_URL = "https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation"
STANDING_PATH = LEDGER_ROOT / "standing.yaml"
TRACKS_PATH = LEDGER_ROOT / "tracks.yaml"
EVIDENCE_DIR = LEDGER_ROOT / "evidence"
PUBLIC_SCORE_FILE = "kaggle-public-score.json"


# --- Inputs -----------------------------------------------------------------------------------


class StandingError(ValueError):
    """`ledger/standing.yaml` is missing a field or holds a value of the wrong type."""


@dataclass
class Standing:
    leaderboard_read_at: datetime
    our_score_at_read: float
    rank: int
    teams: int
    leader_score: float
    prize_line_place: int
    prize_line_score: float
    best_public_read_at: datetime
    best_public: dict[str, float]
    submission_notes: dict[str, str]
    notebook_url: str | None


def _field(data: object, key: str, kind: type | tuple[type, ...], where: str) -> object:
    if not isinstance(data, dict) or key not in data:
        raise StandingError(f"{where}: missing {key!r}")
    value = data[key]
    # bool is an int subclass; a YAML `yes` must not pass for a rank.
    if isinstance(value, bool) or not isinstance(value, kind):
        raise StandingError(f"{where}.{key}: {value!r} is not {kind}")
    return value


def _utc(text: str, where: str) -> datetime:
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise StandingError(f"{where}: {text!r} is not an ISO 8601 time") from exc


def parse_standing(data: object) -> Standing:
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise StandingError("standing: expected a mapping with schema: 1")
    number = (int, float)
    board = _field(data, "leaderboard", dict, "standing")
    best = _field(data, "best_public_per_task", dict, "standing")
    notes = _field(data, "submission_notes", dict, "standing")
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in notes.items()):
        raise StandingError("standing.submission_notes: every key and note must be text")
    notebook = data.get("notebook_url")
    if notebook is not None and not (isinstance(notebook, str) and notebook.startswith("https://")):
        raise StandingError(f"standing.notebook_url: {notebook!r} is not an https URL or null")
    return Standing(
        leaderboard_read_at=_utc(_field(board, "read_at_utc", str, "leaderboard"), "leaderboard"),
        our_score_at_read=float(_field(board, "our_score", number, "leaderboard")),
        rank=_field(board, "rank", int, "leaderboard"),
        teams=_field(board, "teams", int, "leaderboard"),
        leader_score=float(_field(board, "leader_score", number, "leaderboard")),
        prize_line_place=_field(board, "prize_line_place", int, "leaderboard"),
        prize_line_score=float(_field(board, "prize_line_score", number, "leaderboard")),
        best_public_read_at=_utc(_field(best, "read_at_utc", str, "best_public_per_task"),
                                 "best_public_per_task"),
        best_public={t: float(_field(best, t, number, "best_public_per_task")) for t in TASKS},
        submission_notes=dict(notes),
        notebook_url=notebook,
    )


def load_standing(path: Path = STANDING_PATH) -> Standing:
    return parse_standing(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


class TracksError(ValueError):
    """`ledger/tracks.yaml` is missing a field or holds a value of the wrong type."""


# What a track figure can say. "shipped" and "verified" carry a measured ratio; "in work" has none
# yet, so the page never shows a number that our checks have not measured.
FIGURE_STATES = ("shipped", "verified", "in work")


@dataclass
class Figure:
    label: str
    state: str
    value: float | None = None
    note: str = ""


@dataclass
class Track:
    id: str
    name: str
    aim: str
    updated_at: datetime
    figures: list[Figure]


def _text_field(data: object, key: str, where: str) -> str:
    try:
        value = _field(data, key, str, where)
    except StandingError as exc:
        raise TracksError(str(exc)) from None
    if not value.strip():
        raise TracksError(f"{where}.{key}: empty")
    return value.strip()


def _figure(data: object, where: str) -> Figure:
    label = _text_field(data, "label", where)
    state = _text_field(data, "state", where)
    if state not in FIGURE_STATES:
        raise TracksError(f"{where}.state: {state!r} is not one of {FIGURE_STATES}")
    value = data.get("value")
    if state == "in work":
        if value is not None:
            raise TracksError(f"{where}: an 'in work' figure has no value yet; use 'verified'")
    elif isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
        raise TracksError(f"{where}.value: {value!r} is not a positive measured ratio")
    note = data.get("note", "")
    if not isinstance(note, str):
        raise TracksError(f"{where}.note: {note!r} is not text")
    return Figure(label=label, state=state,
                  value=None if value is None else float(value), note=note.strip())


def parse_tracks(data: object) -> list[Track]:
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise TracksError("tracks: expected a mapping with schema: 1")
    raw = data.get("tracks")
    if not isinstance(raw, list) or not raw:
        raise TracksError("tracks.tracks: expected a non-empty list")
    tracks = []
    for i, item in enumerate(raw):
        where = f"tracks[{i}]"
        figures = item.get("figures", []) if isinstance(item, dict) else None
        if not isinstance(figures, list):
            raise TracksError(f"{where}.figures: expected a list")
        try:
            updated = _utc(_field(item, "updated_at_utc", str, where), where)
        except StandingError as exc:
            raise TracksError(str(exc)) from None
        tracks.append(Track(
            id=_text_field(item, "id", where), name=_text_field(item, "name", where),
            aim=_text_field(item, "aim", where), updated_at=updated,
            figures=[_figure(f, f"{where}.figures[{j}]") for j, f in enumerate(figures)]))
    ids = [t.id for t in tracks]
    if len(set(ids)) != len(ids):
        raise TracksError(f"tracks: duplicate track ids in {ids}")
    return tracks


def load_tracks(path: Path = TRACKS_PATH) -> list[Track]:
    return parse_tracks(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def public_scores(manifests: list[RunManifest], evidence_root: Path = EVIDENCE_DIR
                  ) -> dict[str, float]:
    """Kaggle public score per submission, for the submissions whose score has been read back."""
    scores = {}
    for m in submissions(manifests):
        path = Path(evidence_root) / m.candidate_id / PUBLIC_SCORE_FILE
        if path.is_file():
            record = json.loads(path.read_text(encoding="utf-8"))
            scores[m.candidate_id] = float(record["kaggle"]["publicScore"])
    return scores


def submitted_at(m: RunManifest) -> datetime:
    return datetime.fromisoformat(m.submitted_at_utc or m.timestamp_utc)


def featured_candidate(manifests: list[RunManifest]) -> RunManifest | None:
    """The candidate furthest through the pipeline (highest `last_cleared_gate()`), the most
    recent on a tie. The circuit diagram shows it only while nothing has been uploaded; after the
    first upload it shows the latest upload. Kaggle submissions are skipped here.

    `manifests` is oldest first, as `load_manifests` returns it.
    """
    candidates = [m for m in manifests if m.kind == "candidate"]
    if not candidates:
        return None

    def progress(item: tuple[int, RunManifest]) -> tuple[int, int]:
        gate = item[1].last_cleared_gate()
        # The list position breaks ties in favour of the most recent candidate.
        return (GATE_IDS.index(gate) + 1 if gate else 0, item[0])

    return max(enumerate(candidates), key=progress)[1]


@dataclass
class GateCell:
    status: str  # PASS, FAIL, WAIVED, "stale" or "not run"
    reason: str = ""


def gate_cell(manifest: RunManifest | None, gate: str, task: str | None = None) -> GateCell:
    """One gate's state on the manifest's current zip, for one task wire of a per-task gate or
    for the whole zip (`task=None`). A record bound to an earlier zip is "stale": the ledger does
    not count it as cleared (`RunManifest.gate_cleared`)."""
    record = manifest.latest_gate(gate) if manifest is not None else None
    if manifest is None or record is None:
        return GateCell("not run")
    if record.zip_sha256 != manifest.zip_sha256:
        return GateCell("stale", "ran on an earlier version")
    if task is not None and record.status != "WAIVED":
        result = record.details.get("tasks", {}).get(task)
        if isinstance(result, dict) and isinstance(result.get("status"), str):
            status = result["status"]
            return GateCell("PASS") if status == "PASS" else GateCell("FAIL", status)
    return GateCell(record.status, record.reason)


def is_per_task(spec: GateSpec) -> bool:
    return spec.check.endswith(":per_task")


# --- Wording ----------------------------------------------------------------------------------


NUMBER_WORDS = ("no", "one", "two", "three", "four", "five", "six")


def long_date(when: date | datetime) -> str:
    return f"{when.day} {when:%B %Y}"


def checks_sentence(m: RunManifest) -> str:
    """How the latest upload fared on the six automatic checks, in one sentence. Only records
    on the uploaded zip count; a check that neither passed nor was waived is not run."""
    current = [r for g in GATE_IDS if (r := m.latest_gate(g)) and r.zip_sha256 == m.zip_sha256]
    passed = sum(r.status == "PASS" for r in current)
    waived = sum(r.status == "WAIVED" for r in current)
    total = NUMBER_WORDS[len(GATE_IDS)]
    if passed == len(GATE_IDS):
        return f"For the latest upload, all {total} of our automatic checks passed."
    text = f"For the latest upload, {NUMBER_WORDS[passed]} of our {total} automatic checks passed"
    if waived:
        text += (f" and {NUMBER_WORDS[waived]} {'was' if waived == 1 else 'were'} waived, "
                 "with the reason on record")
    return text + "."


# --- HTML -------------------------------------------------------------------------------------


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _time(when: date | datetime) -> str:
    return f'<time datetime="{when:%Y-%m-%d}">{long_date(when)}</time>'


def standing_html(latest_score: float | None, standing: Standing) -> str:
    if latest_score is None:
        return "<p>We have not had a public score back from Kaggle yet.</p>"
    read = _time(standing.leaderboard_read_at)
    if round(latest_score, 5) == round(standing.our_score_at_read, 5):
        rank = f"rank <strong>{standing.rank} of {standing.teams}</strong> teams on {read}"
    else:
        rank = (f"rank {standing.rank} of {standing.teams} teams on {read}, "
                "before this score came in")
    place = standing.prize_line_place
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(place if place < 20 else place % 10, "th")
    return (f"<p>Our public score is <strong>{latest_score:.5f}</strong>, {rank}. The leader "
            f"scores {standing.leader_score:.5f}. The last place that wins prize money "
            f"({place}{suffix}) scores {standing.prize_line_score:.5f}.</p>")


def task_table(latest: RunManifest | None, standing: Standing) -> str:
    rows = []
    for task in TASKS:
        record = latest.tasks.get(task) if latest is not None else None
        ours = f"{record.ratio:.2f}" if record is not None and record.ratio is not None else "—"
        rows.append(f'<tr><th scope="row">{esc(task)}</th><td class="num">{ours}</td>'
                    f'<td class="num">{standing.best_public[task]:.2f}</td>'
                    '<td class="num">1.0</td></tr>')
    return ('<table><thead><tr><th scope="col">Circuit</th><th scope="col" class="num">Ours</th>'
            '<th scope="col" class="num">Best public</th>'
            '<th scope="col" class="num">Reference</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>'
            '<p class="note">Ours: measured on our latest upload with our own run of Google\'s '
            "verifier. Best public: the best figure stated in a public Kaggle notebook, read "
            f"{_time(standing.best_public_read_at)}. Kaggle does not publish scores per circuit, "
            "and the top teams keep theirs private.</p>")


STATE_WORDS = {"PASS": "Passed", "FAIL": "Failed", "WAIVED": "Waived",
               "stale": "Ran on an earlier version", "not run": "Not run"}
STATE_CLASS = {"PASS": "pass", "FAIL": "fail", "WAIVED": "waived", "stale": "stale"}

# The six checks in plain words, for readers who have never seen the gate config. The config's
# own names (`configs/gates/default.yaml`) are written for engineers.
GATE_WORDS = {
    "G0": "File check: every file is well formed and within the rules, before anything runs",
    "G1": "Small test: each circuit gives the right answer on small cases",
    "G2": "Quick estimate: a fast check of each circuit's cost and accuracy",
    "G3": "Google's verifier: the competition's own checker, run in full on our machine",
    "G4": "Real gain: cheaper than everything we had before",
    "G5": "Rebuilt from our code: a clean rebuild matches the upload byte for byte",
}


def state_class(status: str) -> str:
    return STATE_CLASS.get(status, "notrun")


def _ratio(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


# Circuit geometry, in SVG user units. Wires run left to right; gates sit on columns.
VIEW_W = 800
LABEL_X = 108                          # right edge of the wire labels
WIRE_X0, WIRE_X1 = 122, 680            # quantum wires end at the measurement
GATE_X = [170 + 84 * i for i in range(6)]
METER_X = 656
WIRE_Y = [44 + 60 * i for i in range(len(TASKS))]
VIEW_H = WIRE_Y[-1] + 44
GATE_W, GATE_H = 48, 32


def _gate_svg(spec: GateSpec, x: int, y0: float, y1: float, cell: GateCell, title: str) -> str:
    left, top, height = x - GATE_W / 2, y0, y1 - y0
    inner = ""
    if spec.id in UNWAIVABLE_GATES:
        inner = (f'<rect class="inner" x="{left + 4}" y="{top + 4}" width="{GATE_W - 8}" '
                 f'height="{height - 8}"/>')
    return (f'<g class="gate {state_class(cell.status)}"><title>{esc(title)}</title>'
            f'<rect class="box" x="{left}" y="{top}" width="{GATE_W}" height="{height}"/>{inner}'
            f'<text x="{x}" y="{top + height / 2}">{esc(spec.id)}</text></g>')


def circuit_svg(config: GateConfig, shown: RunManifest | None) -> str:
    parts = [
        f'<svg viewBox="0 0 {VIEW_W} {VIEW_H}" role="img" aria-labelledby="circuit-title">',
        '<title id="circuit-title">Our six checks drawn as a quantum circuit: one wire per '
        'circuit, checks G0 to G5 in order, and the measured score of each circuit at the end of '
        'its wire.</title>',
        '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)"><rect class="hatch-bg" width="6" height="6"/>'
        '<line class="hatch-line" x1="0" y1="0" x2="0" y2="6"/></pattern></defs>',
    ]
    for task, y in zip(TASKS, WIRE_Y):
        parts.append(f'<text class="wire-label" x="{LABEL_X}" y="{y}">{esc(task)}</text>')
        parts.append(f'<line class="wire" x1="{WIRE_X0}" y1="{y}" x2="{METER_X}" y2="{y}"/>')
        for dy in (-2, 2):
            parts.append(f'<line class="classical" x1="{METER_X + 18}" y1="{y + dy}" '
                         f'x2="{WIRE_X1 + 8}" y2="{y + dy}"/>')
    for spec, x in zip(config.gates, GATE_X):
        if is_per_task(spec):
            for task, y in zip(TASKS, WIRE_Y):
                cell = gate_cell(shown, spec.id, task)
                title = f"{spec.id} {task}: {STATE_WORDS.get(cell.status, cell.status)}"
                parts.append(_gate_svg(spec, x, y - GATE_H / 2, y + GATE_H / 2, cell,
                                       title + (f" ({cell.reason})" if cell.reason else "")))
        else:
            cell = gate_cell(shown, spec.id)
            title = f"{spec.id}, all circuits: {STATE_WORDS.get(cell.status, cell.status)}"
            parts.append(_gate_svg(spec, x, WIRE_Y[0] - 22, WIRE_Y[-1] + 22, cell,
                                   title + (f" ({cell.reason})" if cell.reason else "")))
    for task, y in zip(TASKS, WIRE_Y):
        parts.append(
            f'<g class="meter"><rect x="{METER_X - 18}" y="{y - 15}" width="36" height="30"/>'
            f'<path d="M {METER_X - 11} {y + 7} A 11 11 0 0 1 {METER_X + 11} {y + 7}"/>'
            f'<line x1="{METER_X}" y1="{y + 7}" x2="{METER_X + 8}" y2="{y - 9}"/></g>')
        record = shown.tasks.get(task) if shown is not None else None
        ratio = record.ratio if record is not None else None
        cls = "ratio" if ratio is None or record.measured else "ratio unmeasured"
        parts.append(f'<text class="{cls}" x="{WIRE_X1 + 16}" y="{y}">{_ratio(ratio)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def gate_list(config: GateConfig, shown: RunManifest | None) -> str:
    items = []
    for spec in config.gates:
        if is_per_task(spec):
            cells = {t: gate_cell(shown, spec.id, t) for t in TASKS}
            statuses = {c.status for c in cells.values()}
            if len(statuses) == 1:
                status = statuses.pop()
                state = STATE_WORDS.get(status, status)
            else:
                status = "FAIL" if "FAIL" in statuses else sorted(statuses)[0]
                state = ", ".join(f"{t} {STATE_WORDS.get(c.status, c.status).lower()}"
                                  for t, c in cells.items())
        else:
            status = gate_cell(shown, spec.id).status
            state = STATE_WORDS.get(status, status)
        never = ('<span class="never">Never waived</span>'
                 if spec.id in UNWAIVABLE_GATES else "")
        items.append(f'<li class="{state_class(status)}"><span class="gid">{esc(spec.id)}</span>'
                     f'<span class="gname">{esc(GATE_WORDS.get(spec.id, spec.name))}</span>'
                     f'<span class="gstate">{esc(state)}</span>{never}</li>')
    return '<ol class="gates">' + "".join(items) + "</ol>"


def checks_html(config: GateConfig, manifests: list[RunManifest],
                shipped: list[RunManifest]) -> str:
    """The gate pipeline drawn as a circuit, for the latest upload; before the first upload, for
    the candidate furthest through the pipeline."""
    if shipped:
        shown = shipped[-1]
        caption = (f"It shows our latest upload, sent on {_time(submitted_at(shown))}. "
                   f"{checks_sentence(shown)}")
    else:
        shown = featured_candidate(manifests)
        caption = ("Nothing is uploaded yet, so this shows the circuits furthest through our "
                   "checks." if shown else "Nothing has entered our checks yet.")
    return f"""<p>Before anything is uploaded, it has to pass six automatic checks in order. The
drawing shows them as a quantum circuit: one wire per circuit, one box per check, and the score of
each circuit at the end of its wire. {caption}</p>
<figure class="circuit">
<div class="circuit-scroll">{circuit_svg(config, shown)}</div>
<figcaption class="legend">
<span><i class="swatch pass"></i>Passed</span>
<span><i class="swatch waived"></i>Waived</span>
<span><i class="swatch fail"></i>Failed</span>
<span><i class="swatch notrun"></i>Not run</span>
<span><i class="swatch never"></i>Never waived</span>
<span>Tall boxes check the whole upload; small ones check each circuit.</span>
</figcaption>
</figure>
{gate_list(config, shown)}"""


def tracks_html(tracks: list[Track]) -> str:
    cards = []
    for t in tracks:
        rows = []
        for f in t.figures:
            value = (f'<span class="fvalue">{f.value:.2f}×</span>' if f.value is not None
                     else "")
            note = f' <span class="fnote">{esc(f.note)}</span>' if f.note else ""
            rows.append(f'<li><span class="flabel">{esc(f.label)}</span>{value}'
                        f'<span class="fstate {f.state.replace(" ", "")}">{esc(f.state)}</span>'
                        f'{note}</li>')
        figures = f'<ul class="figures">{"".join(rows)}</ul>' if rows else ""
        cards.append(f'<article class="track"><h3><span class="tid">{esc(t.id)}</span> '
                     f'{esc(t.name)}</h3><p>{esc(t.aim)}</p>{figures}'
                     f'<p class="note">Updated {_time(t.updated_at)}.</p></article>')
    return ('<p>Our work runs in four tracks. Every number is a score for one circuit, measured '
            "with Google's verifier, where higher is better; <em>shipped</em> means it is in our "
            "latest upload, <em>verified</em> means it passed but is not uploaded, and <em>in "
            "work</em> has no measured number yet.</p>"
            f'<div class="tracks">{"".join(cards)}</div>')


def provenance_html(standing: Standing) -> str:
    notebook = (f' Our <a href="{esc(standing.notebook_url)}">public notebook</a> rebuilds the '
                "entry from source on Kaggle, so anyone can repeat it."
                if standing.notebook_url else
                " A public Kaggle notebook that rebuilds the entry from source is on its way.")
    return f"""<p>Every circuit we upload is regenerated from our own code, which is in the
repository, and checked byte for byte: a clean rebuild must produce exactly the files we
uploaded, and no circuit is ever copied from the competition package. The few input files a
rebuild may read are declared in advance and pinned by their SHA-256 fingerprint, so a changed
input stops the rebuild. Public work we build on is credited with its source and licence. Every
decision and every result, including what did not work, is written into our public
<a href="{REPO_URL}/tree/main/docs/decisions">decisions register</a>, and every upload is recorded
in the <a href="{REPO_URL}/tree/main/ledger">ledger</a> before it is sent. The
<a href="{REPO_URL}">code and full record are on GitHub</a>, next to the
<a href="{KAGGLE_URL}">competition on Kaggle</a>.{notebook}</p>"""


# Only the newest uploads carry their "What changed" note; older rows keep their date and score.
# Each upload adds a row, and this keeps the page under its word budget as the list grows.
NOTED_UPLOADS = 5


def uploads_table(shipped: list[RunManifest], scores: dict[str, float],
                  standing: Standing) -> str:
    if not shipped:
        return "<p>No uploads yet.</p>"
    rows = []
    first_noted = len(shipped) - NOTED_UPLOADS
    for i, m in enumerate(shipped):
        score = scores.get(m.candidate_id)
        shown = f"{score:.5f}" if score is not None else "waiting for Kaggle"
        note = standing.submission_notes.get(m.candidate_id, "") if i >= first_noted else ""
        rows.append(f"<tr><td>{_time(submitted_at(m))}</td><td class=\"num\">{shown}</td>"
                    f"<td>{esc(note)}</td></tr>")
    return ('<table><thead><tr><th scope="col">Date</th><th scope="col" class="num">Public score</th>'
            '<th scope="col">What changed</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def render_page(manifests: list[RunManifest], standing: Standing,
                scores: dict[str, float], *, config: GateConfig | None = None,
                tracks: list[Track] | None = None) -> str:
    config = config if config is not None else load_config()
    tracks = tracks if tracks is not None else load_tracks()
    shipped = sorted(submissions(manifests), key=submitted_at)
    scored = [m for m in shipped if m.candidate_id in scores]
    latest = scored[-1] if scored else None
    links = [f'<a href="{REPO_URL}">Code and full record on GitHub</a>',
             f'<a href="{KAGGLE_URL}">The competition on Kaggle</a>']
    if standing.notebook_url:
        links.append(f'<a href="{esc(standing.notebook_url)}">Our public notebook</a>')

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="description" content="Praxen's entry to Google Quantum AI's Kaggle competition, Verifiable Quantum Circuit Compilation.">
<title>Praxen: Verifiable Quantum Circuit Compilation</title>
<style>{CSS}</style>
</head>
<body>
<main>
<h1>Praxen's entry to Verifiable Quantum Circuit Compilation</h1>
<p><a href="{KAGGLE_URL}">Verifiable Quantum Circuit Compilation</a> is a Kaggle competition run
by Google Quantum AI, open until {_time(DEADLINE)}. Each team sends three quantum circuits, and
the goal is to make them cheaper to run while they still give the right answer.
<strong>invsqrt</strong> is arithmetic: it computes one over a square root.
<strong>dqi</strong> is a decoder that corrects errors. <strong>dfthcsos</strong> is one step of a
chemistry simulation. Each circuit scores the reference cost divided by our cost, and the overall
score is the geometric mean (a kind of average) of the three, so Google's reference circuits
score 1.0 and higher is better.</p>

<section aria-labelledby="standing-h">
<h2 id="standing-h">Where we stand</h2>
{standing_html(scores.get(latest.candidate_id) if latest else None, standing)}
{task_table(latest, standing)}
</section>

<section aria-labelledby="tracks-h">
<h2 id="tracks-h">What we are working on</h2>
{tracks_html(tracks)}
</section>

<section aria-labelledby="checks-h">
<h2 id="checks-h">How each upload is checked</h2>
{checks_html(config, manifests, shipped)}
</section>

<section aria-labelledby="uploads-h">
<h2 id="uploads-h">Our uploads</h2>
{uploads_table(shipped, scores, standing)}
</section>

<section aria-labelledby="how-h">
<h2 id="how-h">Where every circuit comes from</h2>
{provenance_html(standing)}
</section>
</main>
<footer>
<p>{" · ".join(links)}</p>
</footer>
</body>
</html>
"""


CSS = """
:root{--paper:#F7F8FA;--ink:#17202B;--muted:#4A5869;--wire:#6A7B90;--rule:#D5DCE5;
--pass:#1D6B50;--fail:#B3261E;--waived:#946200;--accent:#3446C9;--on-fill:#FFFFFF;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
@media (prefers-color-scheme:dark){:root{--paper:#111821;--ink:#E5EAF1;--muted:#A7B3C2;
--wire:#8494A8;--rule:#2A3542;--pass:#49B98C;--fail:#F0766B;--waived:#D9A93F;--accent:#9AACFF;
--on-fill:#0E141C}}
*,*::before,*::after{box-sizing:border-box}
body{margin:0 auto;max-width:48rem;padding:2rem 1.25rem 3rem;background:var(--paper);
color:var(--ink);font:1.0625rem/1.55 var(--sans)}
a{color:var(--accent);text-underline-offset:.15em}
a:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:2px}
h1{font-size:1.75rem;line-height:1.2;margin:0 0 1rem}
h2{font-size:1.25rem;margin:2.25rem 0 .5rem}
h3{font-size:1.0625rem;margin:0 0 .25rem}
p,ul{margin:.5rem 0}
table{border-collapse:collapse;width:100%;margin:.75rem 0;font-variant-numeric:tabular-nums}
th,td{padding:.4rem .6rem;text-align:left;border-bottom:1px solid var(--rule)}
thead th{color:var(--muted);font-weight:600}
th.num,td.num{text-align:right}
.note{font-size:.875rem;color:var(--muted)}
time{white-space:nowrap}
.tracks{display:grid;grid-template-columns:repeat(auto-fit,minmax(20rem,1fr));gap:1rem;
margin-top:.75rem}
.track{border:1px solid var(--rule);border-radius:6px;padding:.75rem 1rem}
.track p{margin:.25rem 0}
.tid{color:var(--accent)}
.figures{list-style:none;padding:0;margin:.5rem 0}
.figures li{padding:.3rem 0;border-top:1px solid var(--rule)}
.flabel{margin-right:.5rem}
.fvalue{font-weight:700;font-variant-numeric:tabular-nums;margin-right:.5rem}
.fstate{font-size:.8125rem;font-weight:600;padding:0 .4rem;border-radius:3px;
border:1px solid var(--muted);color:var(--muted)}
.fstate.shipped{border-color:var(--pass);color:var(--pass)}
.fstate.verified{border-color:var(--accent);color:var(--accent)}
.fnote{display:block;font-size:.875rem;color:var(--muted)}
.circuit{margin:1rem 0 0}
.circuit-scroll{overflow-x:auto}
.circuit svg{display:block;width:100%;min-width:640px;height:auto}
.wire{stroke:var(--wire);stroke-width:1.5}
.classical{stroke:var(--wire);stroke-width:1.25}
.wire-label{font:600 15px var(--sans);fill:var(--ink);text-anchor:end;dominant-baseline:central}
.gate .box{stroke-width:1.5}
.gate .inner{fill:none;stroke-width:1}
.gate text{font:600 14px var(--sans);text-anchor:middle;dominant-baseline:central}
.gate.pass .box{fill:var(--pass);stroke:var(--pass)}
.gate.fail .box{fill:var(--fail);stroke:var(--fail)}
.gate.pass text,.gate.fail text{fill:var(--on-fill)}
.gate.pass .inner,.gate.fail .inner{stroke:var(--on-fill)}
.gate.waived .box{fill:url(#hatch);stroke:var(--waived)}
.gate.waived text{fill:var(--ink);paint-order:stroke;stroke:var(--paper);stroke-width:4px}
.gate.waived .inner{stroke:var(--waived)}
.gate.notrun .box,.gate.stale .box{fill:var(--paper);stroke-dasharray:4 3}
.gate.notrun .box{stroke:var(--wire)}
.gate.stale .box{stroke:var(--waived)}
.gate.notrun .inner,.gate.stale .inner{stroke:var(--wire)}
.gate.notrun text{fill:var(--muted)}
.gate.stale text{fill:var(--ink)}
.hatch-bg{fill:var(--paper)}
.hatch-line{stroke:var(--waived);stroke-width:3}
.meter rect{fill:var(--paper);stroke:var(--ink);stroke-width:1.5}
.meter path,.meter line{fill:none;stroke:var(--ink);stroke-width:1.5}
.ratio{font:600 16px var(--sans);fill:var(--ink);dominant-baseline:central;
font-variant-numeric:tabular-nums}
.ratio.unmeasured{font-style:italic;fill:var(--muted)}
.legend{display:flex;flex-wrap:wrap;gap:.4rem 1.25rem;margin-top:.75rem;font-size:.9375rem;
color:var(--muted)}
.swatch{display:inline-block;width:1.15em;height:.8em;margin-right:.4em;vertical-align:-.05em;
border:1.5px solid var(--wire)}
.swatch.pass{background:var(--pass);border-color:var(--pass)}
.swatch.fail{background:var(--fail);border-color:var(--fail)}
.swatch.waived{border-color:var(--waived);background:repeating-linear-gradient(45deg,
var(--waived) 0 2px,transparent 2px 5px)}
.swatch.notrun{border-style:dashed}
.swatch.never{border:3px double var(--ink)}
.gates{list-style:none;padding:0;margin:1.25rem 0 0}
.gates li{display:grid;grid-template-columns:2.75rem 1fr auto;gap:.1rem 1rem;align-items:baseline;
padding:.5rem 0;border-top:1px solid var(--rule)}
.gid{font-weight:700}
.gstate{font-weight:600;text-align:right;color:var(--muted)}
.gates .pass .gstate{color:var(--pass)}
.gates .fail .gstate{color:var(--fail)}
.gates .waived .gstate,.gates .stale .gstate{color:var(--waived)}
.never{grid-column:2;font-size:.875rem;color:var(--muted)}
footer{margin-top:2.5rem;padding-top:1rem;border-top:1px solid var(--rule);font-size:.9375rem}
@media (max-width:40rem){.gates li{grid-template-columns:2.75rem 1fr}
.gstate{grid-column:2;text-align:left}}
"""


# --- Entry point ------------------------------------------------------------------------------


def build(out: Path, *, manifests_root: Path = MANIFESTS_DIR, standing_path: Path = STANDING_PATH,
          tracks_path: Path = TRACKS_PATH, config_path: Path = DEFAULT_CONFIG,
          evidence_root: Path = EVIDENCE_DIR) -> Path:
    manifests = load_manifests(manifests_root)
    page = render_page(manifests, load_standing(standing_path),
                       public_scores(manifests, evidence_root),
                       config=load_config(config_path), tracks=load_tracks(tracks_path))
    out.mkdir(parents=True, exist_ok=True)
    path = out / "index.html"
    path.write_text(page, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "public",
                        help="output folder (default: public/, which vercel.json serves)")
    args = parser.parse_args(argv)
    print(f"wrote {build(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
