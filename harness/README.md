# Local verification

See [setup and scoring](../docs/handoffs/p0-4-kickmix-build.md) for prerequisites,
exact commands, expected output, failure behavior and rollback.

- `calibrate_reference.py`: measure a complete fixed-salt local reference baseline.
- `score_local.py SUBMISSION.zip`: G0, full verification, task costs and geometric mean.
- `../ledger/gates/g0_preflight.py SUBMISSION.zip`: file checks without simulation.

A successful G0 check is not a valid circuit or a submission approval.
