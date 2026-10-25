"""Status page: one plain-English screen on our Kaggle entry, as static HTML.

`python -m ledger.status_page --out public` writes `public/index.html`. Vercel runs it on every
push (`vercel.json`) and serves the folder as a static site. The reader is someone who knows
nothing about us (PRA-241), so the page says what the competition is, where we stand, the score
per circuit, our uploads and how we work, and links to the repository for the long version.

Our numbers come from the ledger: the per-task ratios from the latest submission manifest, the
public scores from `ledger/evidence/<submission>/kaggle-public-score.json`. The leaderboard
numbers (rank, leader, prize line, best public per task) and the one-line upload notes come from
`ledger/standing.yaml`, which john-wick updates with every leaderboard snapshot. A malformed
manifest or standing file fails the build instead of showing a wrong page. No JavaScript and no
web fonts: the page is the same for every reader and loads in one request.
"""

from __future__ import annotations

import argparse
import html
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

from ledger.run_manifest import (
    GATE_IDS,
    LEDGER_ROOT,
    MANIFESTS_DIR,
    REPO_ROOT,
    TASKS,
    RunManifest,
    load_manifests,
)
from ledger.scorecard import submissions

DEADLINE = date(2027, 1, 20)  # final Kaggle deadline (README)
REPO_URL = "https://github.com/clduab11/quantum-hackathon"
KAGGLE_URL = "https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation"
STANDING_PATH = LEDGER_ROOT / "standing.yaml"
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


def uploads_table(shipped: list[RunManifest], scores: dict[str, float],
                  standing: Standing) -> str:
    if not shipped:
        return "<p>No uploads yet.</p>"
    rows = []
    for m in shipped:
        score = scores.get(m.candidate_id)
        shown = f"{score:.5f}" if score is not None else "waiting for Kaggle"
        rows.append(f"<tr><td>{_time(submitted_at(m))}</td><td class=\"num\">{shown}</td>"
                    f"<td>{esc(standing.submission_notes.get(m.candidate_id, ''))}</td></tr>")
    return ('<table><thead><tr><th scope="col">Date</th><th scope="col" class="num">Public score</th>'
            '<th scope="col">What changed</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def render_page(manifests: list[RunManifest], standing: Standing,
                scores: dict[str, float]) -> str:
    shipped = sorted(submissions(manifests), key=submitted_at)
    scored = [m for m in shipped if m.candidate_id in scores]
    latest = scored[-1] if scored else None
    checks = f" {checks_sentence(shipped[-1])}" if shipped else ""
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

<section aria-labelledby="uploads-h">
<h2 id="uploads-h">Our uploads</h2>
{uploads_table(shipped, scores, standing)}
</section>

<section aria-labelledby="how-h">
<h2 id="how-h">How we work</h2>
<ul>
<li>Every circuit is rebuilt from our own code, and the rebuild must match the uploaded file
byte for byte.</li>
<li>Every upload is checked with Google's verifier first.{checks}</li>
<li>Everything we decided and every result, including what did not work, is in the repository:
the <a href="{REPO_URL}/tree/main/docs/decisions">decisions</a> and the
<a href="{REPO_URL}/tree/main/ledger">ledger</a>.</li>
</ul>
</section>
</main>
<footer>
<p>{" · ".join(links)}</p>
</footer>
</body>
</html>
"""


CSS = """
:root{--paper:#F7F8FA;--ink:#17202B;--muted:#4A5869;--rule:#D5DCE5;--accent:#3446C9}
@media (prefers-color-scheme:dark){:root{--paper:#111821;--ink:#E5EAF1;--muted:#A7B3C2;
--rule:#2A3542;--accent:#9AACFF}}
*,*::before,*::after{box-sizing:border-box}
body{margin:0 auto;max-width:44rem;padding:2rem 1.25rem 3rem;background:var(--paper);
color:var(--ink);font:1.0625rem/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent);text-underline-offset:.15em}
h1{font-size:1.75rem;line-height:1.2;margin:0 0 1rem}
h2{font-size:1.25rem;margin:2rem 0 .5rem}
p,ul{margin:.5rem 0}
table{border-collapse:collapse;width:100%;margin:.75rem 0;font-variant-numeric:tabular-nums}
th,td{padding:.4rem .6rem;text-align:left;border-bottom:1px solid var(--rule)}
thead th{color:var(--muted);font-weight:600}
th.num,td.num{text-align:right}
.note{font-size:.875rem;color:var(--muted)}
footer{margin-top:2.5rem;padding-top:1rem;border-top:1px solid var(--rule);font-size:.9375rem}
"""


# --- Entry point ------------------------------------------------------------------------------


def build(out: Path, *, manifests_root: Path = MANIFESTS_DIR, standing_path: Path = STANDING_PATH,
          evidence_root: Path = EVIDENCE_DIR) -> Path:
    manifests = load_manifests(manifests_root)
    page = render_page(manifests, load_standing(standing_path),
                       public_scores(manifests, evidence_root))
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
