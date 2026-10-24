# ledger/

Submission ledger: the proof layer. Every candidate, verifier run and Kaggle submission leaves a manifest that a
stranger can re-check. Schema and rules: [`docs/ledger-schema.md`](../docs/ledger-schema.md).

| Module | Role |
| --- | --- |
| `run_manifest.py` | Manifest record, reader and writer (ported from qrc-thresher `proof/run_manifest.py`) |
| `benchmark_health.py` | Clean-worktree rebuild and hash comparison, plus ledger self-checks (ported from qrc-thresher) |
| `evidence.py` | Verifier summaries and log hashes folded into a manifest |
| `scorecard.py` | Table of all manifests; 3-per-UTC-day submission cap |
| `archive.py` | Safe zip extraction and deterministic zip builds |
| `gates/runner.py`, `gates/checks.py` | G0–G5 runner, config-driven from `configs/gates/*.yaml` |
| `examples/` | Sample manifest for the reference submission, with its verifier logs |

```
uv run python -m ledger.gates.runner new --zip cand.zip --candidate-id cand-001 --provenance prov.yaml
uv run python -m ledger.gates.runner run --manifest ledger/manifests/candidates/cand-001.json --zip cand.zip
uv run python -m ledger.scorecard               # table
uv run python -m ledger.scorecard --check-slot  # before every Kaggle submission
uv run python -m ledger.benchmark_health        # self-checks
```

`manifests/` (with `index.csv`), `evidence/` and the queue pointers are committed. Zips, `.kmb`, `.npz` and competition data
are never committed; their SHA-256 is.
