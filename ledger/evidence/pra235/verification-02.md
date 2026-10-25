# Integrated refit verification (2026-10-25)

- `uv sync`: passed in this worktree (Python 3.13.13).
- `PYTHONPATH=/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation/kickmix uv run pytest -q`: **269 passed, 1 skipped in 65.93s**; `pytest-03.txt`.
- `uv run pytest tests/test_factor_refit_v2.py tests/test_factor_pipeline.py -q`: **20 passed in 0.33s**.
- `uv run python -m ledger.registers check`: **OK registers: 176 decisions, 4 notice files, legacy index unchanged**.
- `git diff --check`: passed.
- All 10 jobs in `plan-floor.json`, `plan-gradual.json`, `plan-public.json` passed the pipeline's pinned-input dry run. No output was written by these validations.

Real pipeline: `pipeline-smoke-01.json` records the two-iteration schedule
`--shapes 6,144,127 1,496,384 --steps 2 --offset-steps 2 --maxcor 20
--bits 12 11 10 9 8 --quantize-bits 11 10 --quantized-steps 2
--checkpoint-every 1`. Runtime 126.951s; larger shapes miss accuracy.
This validates wiring, not feasibility. `pra235-v2-regression-01.json` retains
the exact original cc7dd377 compressed checkpoint under default numerical settings.

Real batch command:

```sh
uv run python -m tasks.dfthcsos.run_experiments --plan ledger/evidence/pra235/plan-smoke.json --out /home/cld-main/work/vqcc-data/pra235-batch-smoke-01
```

Exit 0. `batch-smoke-01.json`: status complete, child exit 0, 38.0786s.
`batch-control-01.json` contains the complete numerical report.

Good dry run with `plan-floor.json` prints jobs `long-1000`, `penalty-zero`,
`penalty-low`, `penalty-standard`, `penalty-high`, exit 0.
Same command with existing output `pra235-v2-smoke-01` exits 2:
`run_experiments.py: error: output exists; use a new directory`.
Pipeline `--bits 12 --quantize-bits 10 --dry-run` exits 1:
`factor pipeline: quantize bits must be included in measured --bits`; no output created.
A scratch batch with `--bits 6` exits 1 and prints
`experiment baseline-control failed; inspect its log`; child exit 2 and
status error are persisted in `batch-negative-01.json`.

The earlier deliberate zero-gradient mutation failed the independent gradient
test; restored implementation passes. New tests exercise all three optimizer
variants, checkpoint exclusivity/unverified marking and batch path boundaries.
