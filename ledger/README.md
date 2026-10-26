# ledger/

Submission ledger: the proof layer. Every candidate, verifier run and Kaggle submission leaves a manifest that a
stranger can re-check. Schema and rules: [`docs/ledger-schema.md`](../docs/ledger-schema.md).

| Module | Role |
| --- | --- |
| `run_manifest.py` | Manifest record, reader and writer (ported from qrc-thresher `proof/run_manifest.py`) |
| `benchmark_health.py` | Clean-worktree rebuild and hash comparison, plus ledger self-checks (ported from qrc-thresher) |
| `evidence.py` | Verifier summaries and log hashes folded into a manifest |
| `scorecard.py` | Table of all manifests; 3-per-UTC-day submission cap enforced before the upload (`reserve` / `submit` / `record` / `reconcile`, PRA-211) |
| `archive.py` | Safe zip extraction and deterministic zip builds |
| `gates/runner.py`, `gates/checks.py` | G0–G5 runner, config-driven from `configs/gates/*.yaml` |
| `status_page.py` | One-screen public status page (standing, score per circuit, the four tracks, the G0–G5 gate circuit for the latest upload, uploads, provenance) that Vercel builds on every push (`vercel.json`); leaderboard numbers and upload notes come from `standing.yaml`, track figures from `tracks.yaml` (schemas in `docs/ledger-schema.md`) |
| `examples/` | Sample manifest for the reference submission, with its verifier logs |

```
uv run python -m ledger.gates.runner new --zip cand.zip --candidate-id cand-001 --provenance prov.yaml
uv run python -m ledger.gates.runner run --manifest ledger/manifests/candidates/cand-001.json --zip cand.zip
uv run python -m ledger.scorecard               # table
uv run python -m ledger.scorecard --check-slot  # slots left today, counting pending reservations
uv run python -m ledger.scorecard submit --candidate ledger/manifests/candidates/cand-001.json \
    --zip ledger/queue/cand-001.zip --upload-command '<uploader>'   # the only upload path: reserve, upload, record
uv run python -m ledger.scorecard reserve --candidate <manifest>       # before an upload made elsewhere ...
uv run python -m ledger.scorecard record --candidate <manifest> --kaggle-id <id> --reservation <file>  # ... then this
uv run python -m ledger.scorecard reconcile --reservation <file> --failed --reason '<why>'  # free a failed attempt's slot
uv run python -m ledger.benchmark_health        # self-checks
uv run python -m ledger.status_page             # public/index.html, as Vercel builds it
```

`manifests/` (without the derived `index.csv`, PRA-210; resolved slot reservations included), `evidence/` and the queue pointers are committed. Zips, `.kmb`, `.npz` and competition data
are never committed; their SHA-256 is.
