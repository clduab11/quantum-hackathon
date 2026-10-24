"""Status page: the gate pipeline, scorecard, Kaggle cap and decisions register as static HTML.

`python -m ledger.status_page --out public` writes `public/index.html`. Vercel runs it on every
push (`vercel.json`) and serves the folder as a static site behind Vercel login. Every number on
the page comes from the ledger modules imported here, so the page cannot disagree with
`python -m ledger.scorecard`; a malformed manifest fails the build instead of showing a wrong
ledger. Only committed manifests appear, so a run that is not committed is not on the page.

Two values move with the clock rather than the commit: days to the deadline and Kaggle slots
left today. The page embeds their inputs and a short script recomputes them in the browser; the
HTML carries the build-time values for readers without JavaScript.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from ledger.gates.runner import DEFAULT_CONFIG, GateConfig, GateSpec, load_config
from ledger.run_manifest import (
    GATE_IDS,
    MANIFESTS_DIR,
    REPO_ROOT,
    TASKS,
    UNWAIVABLE_GATES,
    RunManifest,
    git_branch,
    git_commit_hash,
    load_manifests,
)
from ledger.scorecard import (
    DAILY_CAP,
    best_geometric_mean,
    best_per_task,
    build_rows,
    slots_left,
    submissions_per_utc_day,
)

DECISIONS_MD = REPO_ROOT / "docs" / "DECISIONS.md"
DEADLINE = date(2027, 1, 20)  # final Kaggle deadline (README)
REPO_URL = "https://github.com/clduab11/quantum-hackathon"


# --- Inputs -----------------------------------------------------------------------------------


@dataclass
class Decision:
    date: str
    id: str
    decision: str
    evidence: str
    status: str


def parse_decisions(text: str) -> list[Decision]:
    """Rows of the register table in `docs/DECISIONS.md`, in file order. Cells may contain
    escaped pipes (`\\|`); the header and separator rows are skipped."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line[1:-1])]
        if len(cells) != 5 or cells[0] == "date" or set(cells[0]) <= set("-: "):
            continue
        rows.append(Decision(*cells))
    return rows


def status_tone(status: str) -> str:
    """How the page reads a free-text register status: "open" (unresolved), "pending" (waiting
    on review or agreement), "settled", or "neutral" for wording it does not recognise."""
    text = status.lower()
    if "unresolved" in text:
        return "open"
    if "pending" in text:
        return "pending"
    if re.search(r"\b(accepted|verified|corrected|implemented|superseded)\b", text):
        return "settled"
    return "neutral"


def featured_candidate(manifests: list[RunManifest]) -> RunManifest | None:
    """The candidate whose gates the circuit at the top of the page shows: the one furthest
    through the pipeline (highest `last_cleared_gate()`), the most recent on a tie, so the page
    shows the candidate closest to a shippable zip. Kaggle submissions are copies of candidates
    that already shipped and are skipped. None (no candidates) draws every gate as not run.

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
    for the whole candidate (`task=None`). A record bound to an earlier zip is "stale": the
    ledger does not count it as cleared (`RunManifest.gate_cleared`)."""
    record = manifest.latest_gate(gate) if manifest is not None else None
    if manifest is None or record is None:
        return GateCell("not run")
    if record.zip_sha256 != manifest.zip_sha256:
        return GateCell("stale", "ran on an earlier zip")
    if task is not None and record.status != "WAIVED":
        result = record.details.get("tasks", {}).get(task)
        if isinstance(result, dict) and isinstance(result.get("status"), str):
            status = result["status"]
            return GateCell("PASS") if status == "PASS" else GateCell("FAIL", status)
    return GateCell(record.status, record.reason)


def is_per_task(spec: GateSpec) -> bool:
    return spec.check.endswith(":per_task")


def deadline_sentence(today: date, deadline: date = DEADLINE) -> str:
    days = (deadline - today).days
    when = f"{deadline.day} {deadline:%B %Y}"
    if days > 1:
        return f"{days} days to the final deadline, {when}."
    if days == 1:
        return f"1 day to the final deadline, {when}."
    if days == 0:
        return f"The final deadline is today, {when}."
    return f"The final deadline passed on {when}."


@dataclass
class BuildInfo:
    commit: str
    branch: str
    built_at: datetime


def build_info(now: datetime) -> BuildInfo:
    """Vercel's system variables when building there, the local checkout otherwise."""
    commit = os.environ.get("VERCEL_GIT_COMMIT_SHA") or git_commit_hash()
    branch = os.environ.get("VERCEL_GIT_COMMIT_REF") or git_branch()
    return BuildInfo(commit=commit, branch=branch, built_at=now)


# --- HTML -------------------------------------------------------------------------------------


STATE_WORDS = {"PASS": "Passed", "FAIL": "Failed", "WAIVED": "Waived",
               "stale": "Ran on an earlier zip", "not run": "Not run"}
STATE_CLASS = {"PASS": "pass", "FAIL": "fail", "WAIVED": "waived", "stale": "stale"}
DECISION_ID = re.compile(r"\bD-(?:[A-Z0-9]+-)*\d+\b")
CODE_SPAN = re.compile(r"`([^`]+)`")


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def state_class(status: str) -> str:
    return STATE_CLASS.get(status, "notrun")


def inline(text: str, known_ids: frozenset[str] = frozenset()) -> str:
    """Escape register text, render `code` spans and link decision ids to their rows."""
    out = []
    for i, part in enumerate(CODE_SPAN.split(text)):
        if i % 2:
            out.append(f"<code>{esc(part)}</code>")
        else:
            out.append(DECISION_ID.sub(
                lambda m: f'<a href="#{m[0]}">{m[0]}</a>' if m[0] in known_ids else m[0],
                esc(part)))
    return "".join(out)


def _ratio(value: float | None) -> str:
    return "—" if value is None else f"{value:.4f}"


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


def circuit_svg(config: GateConfig, featured: RunManifest | None) -> str:
    parts = [
        f'<svg viewBox="0 0 {VIEW_W} {VIEW_H}" role="img" aria-labelledby="circuit-title">',
        '<title id="circuit-title">Gate pipeline drawn as a circuit: one wire per task, gates '
        'G0 to G5 in order, a measured ratio at the end of each wire.</title>',
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
                cell = gate_cell(featured, spec.id, task)
                title = f"{spec.id} {task}: {STATE_WORDS.get(cell.status, cell.status)}"
                parts.append(_gate_svg(spec, x, y - GATE_H / 2, y + GATE_H / 2, cell,
                                       title + (f" ({cell.reason})" if cell.reason else "")))
        else:
            cell = gate_cell(featured, spec.id)
            title = f"{spec.id}, all tasks: {STATE_WORDS.get(cell.status, cell.status)}"
            parts.append(_gate_svg(spec, x, WIRE_Y[0] - 22, WIRE_Y[-1] + 22, cell,
                                   title + (f" ({cell.reason})" if cell.reason else "")))
    for task, y in zip(TASKS, WIRE_Y):
        parts.append(
            f'<g class="meter"><rect x="{METER_X - 18}" y="{y - 15}" width="36" height="30"/>'
            f'<path d="M {METER_X - 11} {y + 7} A 11 11 0 0 1 {METER_X + 11} {y + 7}"/>'
            f'<line x1="{METER_X}" y1="{y + 7}" x2="{METER_X + 8}" y2="{y - 9}"/></g>')
        record = featured.tasks.get(task) if featured is not None else None
        ratio = record.ratio if record is not None else None
        cls = "ratio" if ratio is None or record.measured else "ratio unmeasured"
        parts.append(f'<text class="{cls}" x="{WIRE_X1 + 16}" y="{y}">{_ratio(ratio)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def gate_list(config: GateConfig, featured: RunManifest | None) -> str:
    items = []
    for spec in config.gates:
        if is_per_task(spec):
            cells = {t: gate_cell(featured, spec.id, t) for t in TASKS}
            statuses = {c.status for c in cells.values()}
            if len(statuses) == 1:
                status = statuses.pop()
                state = STATE_WORDS.get(status, status)
            else:
                status = "FAIL" if "FAIL" in statuses else sorted(statuses)[0]
                state = ", ".join(f"{t} {STATE_WORDS.get(c.status, c.status).lower()}"
                                  for t, c in cells.items())
        else:
            status = gate_cell(featured, spec.id).status
            state = STATE_WORDS.get(status, status)
        never = ('<span class="never">Never waived</span>'
                 if spec.id in UNWAIVABLE_GATES else "")
        items.append(f'<li class="{state_class(status)}"><span class="gid">{esc(spec.id)}</span>'
                     f'<span class="gname">{esc(spec.name)}</span>'
                     f'<span class="gstate">{esc(state)}</span>{never}</li>')
    return '<ol class="gates">' + "".join(items) + "</ol>"


def scorecard_table(manifests: list[RunManifest]) -> str:
    if not manifests:
        return ('<p>No candidates in the ledger yet. Start one with '
                '<code>uv run python -m ledger.gates.runner new --zip cand.zip --candidate-id '
                'cand-001 --provenance prov.yaml</code> and commit its manifest.</p>')
    best = best_per_task(manifests)
    head = ("<tr><th>Candidate</th><th>Kind</th>"
            + "".join(f'<th class="num">{esc(t)}</th>' for t in TASKS)
            + '<th class="num">Geo. mean</th><th>Measured</th><th>Last gate</th>'
            "<th>Kaggle id</th></tr>")
    body = []
    for row in build_rows(manifests):
        cells = []
        for task in TASKS:
            top = best[task]
            is_best = (row.kind == "candidate" and top is not None
                       and top[0] == row.candidate_id and row.ratios[task] == top[1])
            cells.append(f'<td class="num{" best" if is_best else ""}">'
                         f"{_ratio(row.ratios[task])}</td>")
        body.append(
            f"<tr><td>{esc(row.candidate_id)}</td><td>{esc(row.kind)}</td>{''.join(cells)}"
            f'<td class="num">{_ratio(row.geometric_mean)}</td>'
            f"<td>{'yes' if row.measured else 'no'}</td><td>{esc(row.last_gate or '—')}</td>"
            f"<td>{esc(row.kaggle_submission_id or '—')}</td></tr>")
    return (f'<div class="table-scroll"><table><thead>{head}</thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>'
            '<p class="note">Bold marks the best measured ratio per task. Unmeasured numbers '
            "never count.</p>")


def decisions_list(decisions: list[Decision]) -> str:
    ids = frozenset(d.id for d in decisions)
    tones = [status_tone(d.status) for d in decisions]
    open_ids = [d.id for d, tone in zip(decisions, tones) if tone == "open"]
    summary = (f"{len(decisions)} entries: {tones.count('open')} open, "
               f"{tones.count('pending')} waiting on review or agreement, "
               f"{tones.count('settled')} settled.")
    if open_ids:
        summary += " Open: " + ", ".join(f'<a href="#{esc(i)}">{esc(i)}</a>' for i in open_ids) + "."
    items = []
    for d, tone in zip(decisions, tones):
        items.append(
            f'<li class="decision {tone}" id="{esc(d.id)}">'
            f'<p class="dmeta"><span class="did">{esc(d.id)}</span>'
            f'<time datetime="{esc(d.date)}">{esc(d.date)}</time>'
            f'<span class="dstatus">{esc(d.status)}</span></p>'
            f'<p class="dtext">{inline(d.decision, ids)}</p>'
            f'<p class="devidence">Evidence: {inline(d.evidence, ids)}</p></li>')
    return f'<p>{summary}</p><ol class="decisions">{"".join(items)}</ol>'


def render_page(manifests: list[RunManifest], config: GateConfig, decisions: list[Decision],
                build: BuildInfo) -> str:
    now = build.built_at
    featured = featured_candidate(manifests)
    if featured is None:
        caption = "No candidate has entered the pipeline yet, so every gate shows as not run."
    else:
        caption = (f"Showing {esc(featured.candidate_id)}, last cleared gate "
                   f"{esc(featured.last_cleared_gate() or 'none')}. Geometric mean "
                   f"{_ratio(featured.geometric_mean)}.")
    best_gm = best_geometric_mean(manifests)
    if best_gm is not None:
        caption += (f" Best fully measured geometric mean in the ledger: {best_gm[1]:.4f} "
                    f"({esc(best_gm[0])}).")
    per_day = submissions_per_utc_day(manifests)
    history = ("".join(f"<li>{day.isoformat()}: {count}</li>" for day, count in per_day.items())
               or "<li>No submissions yet.</li>")
    clock = json.dumps({
        "deadline": DEADLINE.isoformat(),
        "deadlineText": f"{DEADLINE.day} {DEADLINE:%B %Y}",
        "cap": DAILY_CAP,
        "submissionsPerUtcDay": {day.isoformat(): n for day, n in per_day.items()},
    }).replace("</", "<\\/")
    commit = build.commit.removesuffix("-dirty")
    short = commit[:7] + ("-dirty" if build.commit.endswith("-dirty") else "")
    commit_html = (f'<a href="{REPO_URL}/commit/{esc(commit)}">{esc(short)}</a>'
                   if re.fullmatch(r"[0-9a-f]{40}", commit) else esc(short))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>quantum-hackathon status</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@400;600;700&family=STIX+Two+Text:wght@400;600&display=swap">
<style>{CSS}</style>
</head>
<body>
<div class="page">
<header>
<p class="repo"><a href="{REPO_URL}">clduab11/quantum-hackathon</a></p>
<h1>Verifiable Quantum Circuit Compilation</h1>
<p class="lede">Praxen's entry to the Google Quantum AI Kaggle competition. Each task scores
baseline cost divided by our cost, and the entry scores the geometric mean of the three, so the
reference circuits score 1.0. One failing task rejects the whole submission.</p>
<p class="deadline" id="deadline">{esc(deadline_sentence(now.date()))}</p>
</header>
<main>
<section aria-labelledby="pipeline-h">
<h2 id="pipeline-h">Gate pipeline</h2>
<p>{caption}</p>
<figure class="circuit">
<div class="circuit-scroll">{circuit_svg(config, featured)}</div>
<figcaption class="legend">
<span><i class="swatch pass"></i>Passed</span>
<span><i class="swatch waived"></i>Waived</span>
<span><i class="swatch fail"></i>Failed</span>
<span><i class="swatch notrun"></i>Not run</span>
<span><i class="swatch never"></i>Never waived</span>
<span>Tall gates judge the whole zip; small ones run per task.</span>
</figcaption>
</figure>
{gate_list(config, featured)}
</section>
<section aria-labelledby="scorecard-h">
<h2 id="scorecard-h">Scorecard</h2>
{scorecard_table(manifests)}
</section>
<section aria-labelledby="kaggle-h">
<h2 id="kaggle-h">Kaggle submissions</h2>
<p><span id="slots-left">{slots_left(manifests, now)}</span> of {DAILY_CAP} submissions left
today (UTC). Only john-wick submits, and every submission is recorded in the ledger.</p>
<ul class="history">{history}</ul>
</section>
<section aria-labelledby="decisions-h">
<h2 id="decisions-h">Decisions register</h2>
{decisions_list(decisions)}
</section>
</main>
<footer>
<p>Built from {commit_html} on {esc(build.branch)} at {now:%Y-%m-%d %H:%M} UTC. Vercel rebuilds
this page on every push from the committed ledger, gate config and decisions register.</p>
</footer>
</div>
<script type="application/json" id="clock-inputs">{clock}</script>
<script>{SCRIPT}</script>
</body>
</html>
"""


CSS = """
:root{--paper:#F5F7FA;--ink:#17202B;--muted:#4A5869;--wire:#6A7B90;--rule:#D5DCE5;
--pass:#1D6B50;--fail:#B3261E;--waived:#946200;--accent:#3446C9;--on-fill:#FFFFFF;
--serif:"STIX Two Text","STIX Two",Cambria,"Times New Roman",serif;
--sans:"Atkinson Hyperlegible Next","Atkinson Hyperlegible",system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root{--paper:#111821;--ink:#E5EAF1;--muted:#A7B3C2;
--wire:#8494A8;--rule:#2A3542;--pass:#49B98C;--fail:#F0766B;--waived:#D9A93F;--accent:#9AACFF;
--on-fill:#0E141C}}
*,*::before,*::after{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
font-size:1.0625rem;line-height:1.55;-webkit-text-size-adjust:100%}
.page{max-width:68rem;margin:0 auto;padding:3rem max(1rem,4vw) 4rem}
a{color:var(--accent);text-underline-offset:.15em}
a:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:2px}
h1,h2{font-family:var(--serif);font-weight:600;line-height:1.15;margin:0}
h1{font-size:clamp(2rem,1.25rem + 3vw,3rem);letter-spacing:-.01em;max-width:20ch}
h2{font-size:1.625rem;margin-bottom:.75rem}
p{max-width:66ch;margin:.5rem 0}
code{font-family:ui-monospace,"Cascadia Mono",Menlo,Consolas,monospace;font-size:.875em;
overflow-wrap:anywhere}
.repo{margin:0 0 1rem;font-size:.9375rem}
.lede{font-family:var(--serif);font-size:1.25rem;line-height:1.5;max-width:60ch;margin:1rem 0 .5rem}
.deadline{color:var(--muted)}
section{margin-top:3.5rem}
.note{font-size:.875rem;color:var(--muted)}
.circuit{margin:1.5rem 0 0}
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
.gates{list-style:none;padding:0;margin:1.75rem 0 0}
.gates li{display:grid;grid-template-columns:2.75rem 1fr auto;gap:.1rem 1rem;align-items:baseline;
padding:.55rem 0;border-top:1px solid var(--rule)}
.gid{font-weight:700}
.gstate{font-weight:600;text-align:right;color:var(--muted)}
.gates .pass .gstate{color:var(--pass)}
.gates .fail .gstate{color:var(--fail)}
.gates .waived .gstate,.gates .stale .gstate{color:var(--waived)}
.never{grid-column:2;font-size:.875rem;color:var(--muted)}
.table-scroll{overflow-x:auto}
table{border-collapse:collapse;min-width:100%;font-size:.9375rem;font-variant-numeric:tabular-nums}
th,td{padding:.5rem .75rem;text-align:left;border-bottom:1px solid var(--rule);white-space:nowrap}
th{font-weight:600;color:var(--muted)}
.num{text-align:right}
td.best{font-weight:700}
.history{padding-left:1.25rem;margin:.5rem 0 0;font-variant-numeric:tabular-nums}
.decisions{list-style:none;padding:0;margin:1.25rem 0 0}
.decision{margin:0 0 1.25rem;padding:.25rem 0 .25rem 1rem;border-left:3px solid var(--rule)}
.decision.open{border-left-color:var(--fail)}
.decision.pending{border-left-color:var(--waived)}
.decision.settled{border-left-color:var(--pass)}
.decision:target{background:color-mix(in srgb,var(--accent) 9%,transparent)}
.dmeta{display:flex;flex-wrap:wrap;gap:.2rem 1rem;margin:0;font-size:.9375rem;color:var(--muted)}
.did{font-weight:700;color:var(--ink)}
.decision.open .dstatus{color:var(--fail);font-weight:600}
.dtext{font-family:var(--serif);font-size:1.0625rem;line-height:1.6;max-width:72ch;margin:.3rem 0 0}
.devidence{font-size:.875rem;color:var(--muted);margin:.3rem 0 0}
footer{margin-top:4rem;padding-top:1rem;border-top:1px solid var(--rule);font-size:.875rem;
color:var(--muted)}
@media (max-width:40rem){.gates li{grid-template-columns:2.75rem 1fr}
.gstate{grid-column:2;text-align:left}}
"""

SCRIPT = """
(() => {
  const inputs = JSON.parse(document.getElementById("clock-inputs").textContent);
  const now = new Date();
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const [y, m, d] = inputs.deadline.split("-").map(Number);
  const days = Math.round((Date.UTC(y, m - 1, d) - today) / 86400000);
  const when = inputs.deadlineText;
  document.getElementById("deadline").textContent =
    days > 1 ? `${days} days to the final deadline, ${when}.`
    : days === 1 ? `1 day to the final deadline, ${when}.`
    : days === 0 ? `The final deadline is today, ${when}.`
    : `The final deadline passed on ${when}.`;
  const used = inputs.submissionsPerUtcDay[now.toISOString().slice(0, 10)] || 0;
  document.getElementById("slots-left").textContent = String(Math.max(0, inputs.cap - used));
})();
"""


# --- Entry point ------------------------------------------------------------------------------


def build(out: Path, *, manifests_root: Path = MANIFESTS_DIR, config_path: Path = DEFAULT_CONFIG,
          decisions_md: Path = DECISIONS_MD, now: datetime | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    page = render_page(load_manifests(manifests_root), load_config(config_path),
                       parse_decisions(decisions_md.read_text(encoding="utf-8")), build_info(now))
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
