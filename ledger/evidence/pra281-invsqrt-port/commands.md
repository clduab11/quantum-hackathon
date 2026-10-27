# PRA-284 commands and environment

Repository: `/home/cld-main/work/.paperclip-worktrees/quantum-hackathon/op-vqcc/PRA-281-1-invsqrt-port-candidate`.
Branch: `op-vqcc/PRA-281-1-invsqrt-port-candidate`, rebased onto `main` `33c8f82`.
The worktree venv uses torch 2.8.0+cu128 and reports one available CUDA device.

## Exact zip and real G0–G5

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 UV_NO_SYNC=1 \
  PYTHONPATH=. uv run python -u ledger/evidence/pra281-invsqrt-port/run_candidate.py
```

Run from a clean tree at `ab06f05`, so the manifest's generator commit is a
clean 40-hex hash. The script checks the parent zip against the
`pra280-rustad` manifest. It takes `invsqrt.kmb` (checked against
`17fc223d…`) from the superseded PRA-250-based zip, which holds clean rebuild 1.
It builds the zip deterministically with `ledger.archive.build_zip`, asserts that
the DQI and chemistry file maps equal the parent's, then runs the cascade.
G5 regenerates all three tasks from the committed generators. Neither zip is an
input to any generator. Result: exit 0, all six gates PASS,
`shipping_problems: []`, 584.3 s (`gates.log`, `pipeline.json`).

The runner resumes existing records and does not rerun cleared gates. A fresh
verification needs a new candidate manifest/id from the same zip.

A first attempt from a dirty tree recorded generator commit
`872b22c…-dirty`. That is a certain G5 provenance failure, so it was stopped
during G3, before any gate failed. Its manifest and zip were deleted, and the
cascade was rerun from a clean tree.

## Tests and registers

```text
$ uv sync && OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run pytest
Uninstalled 31 packages in 547ms
397 passed, 11 skipped in 87.71s (0:01:27)
(exit 0)
$ uv sync --group gpu && OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 UV_NO_SYNC=1 uv run pytest -rs
421 passed, 3 skipped, 1 warning in 144.47s (0:02:24)
(exit 0)
$ uv run --no-sync pytest tests/test_invsqrt_public_port_gates.py tests/test_invsqrt_public_port.py -q
11 passed in 2.16s
$ uv run --no-sync python -m ledger.registers check
OK registers: 277 decisions, 7 notice files, legacy index unchanged
```

The 11 skips in the plain run are optional-dependency imports (jax, torch,
nbformat, the gpu group). With the gpu group, the 3 remaining skips are
existing opt-in conditions (nbformat, pinned JAX integration, JAX smoke). The
warning is the existing Torch TensorFloat32 performance suggestion. Raw output
is in `pytest.log`.

## Clean rebuilds (circuit evidence, base-independent)

The two clean CUDA rebuilds at `6babc95` are recorded in `clean-rebuilds.json`,
`rebuild-1.log` and `rebuild-2.log`. Both gave `17fc223d…`.

## Rollback

```sh
PYTHONPATH=. uv run python ledger/evidence/pra281-invsqrt-port/rollback.py --repo .          # the rollback
PYTHONPATH=. uv run python ledger/evidence/pra281-invsqrt-port/rollback.py --rehearse --ref HEAD   # staging rehearsal
```

The recorded rehearsal output is in `rollback-check.json`; see the addendum in
`report.md`.

No reservation, upload, main push, merge, licence check, forbidden-source read,
or live-stack action occurred.
