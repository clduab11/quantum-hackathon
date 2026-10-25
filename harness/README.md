# Local verification

See [setup and scoring](../docs/handoffs/p0-4-kickmix-build.md) for prerequisites,
exact commands, expected output, failure behavior and rollback.

- `calibrate_reference.py`: measure a complete fixed-salt local reference baseline.
- `score_local.py SUBMISSION.zip`: G0, full verification, task costs and geometric mean.
- `run_notebook.py NOTEBOOK.ipynb [--timeout SECONDS]`: execute a notebook headless and write outputs back in place
  (`uv run --group notebooks python harness/run_notebook.py ...`; D-PRA206-01).
- `../ledger/gates/g0_preflight.py SUBMISSION.zip`: file checks without simulation.

A successful G0 check is not a valid circuit or a submission approval.
