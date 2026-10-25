# Factor refit v2: experiment in progress

PRA-235 extends the Google-only pipeline with larger-group initialization and
weight fitting against rounded vectors. The integrated CLI is tested;
the full experiment matrix is still in progress. The 12-bit floor has passed
and was handed to PRA-237 (details below). Construction probes alone do not
establish accuracy; no shipping claim is made.

## Long-fit control

Prerequisites: WSL, `uv sync`, and the original input trees matching
`ledger/manifests/inputs/pra198-google-v4.json`. From this repository:

```sh
uv run python -m tasks.dfthcsos.factor_pipeline \
  --starter /home/cld-main/work/vqcc-data/starter-kit \
  --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation \
  --out /home/cld-main/work/vqcc-data/pra235-floor-long-01 \
  --shapes 65,60,30 --bits 12 11 10 9 8 \
  --steps 1000 --offset-steps 100 --dry-run
```

Remove `--dry-run` only for a new output path. The CLI refuses overwrite and
checks input hashes before imports. It writes only that output directory. Exit 0 means the final requested shape has a point with both errors at most
0.019 Ha and the strict Lambda/gap floors passing. Exit 3 is a measured miss. Every bit width is
independently encoded and evaluated by the unmodified competition verifier.
The resource prediction already uses `heuristic_costs`, which calls the pinned
`costs_prepare.py` `SpinFreeData_V1`, and adds ordinary-QROM ANGLE lookup costs.
It does not claim the public banked lookup costs.

Do not edit the source modules hashed by a running pipeline: the completion
check will reject a changed source. For later long jobs, use a source snapshot
from a committed revision and record that revision and output path.

## Regroup initialization

`factor_reseed.regroup(params, R, B, C)` merges consecutive existing groups,
retains the B largest weight-norm bases per merged group, then truncates the
augmented `[W; H2_I]` SVD with deterministic signs. This permits larger B/C
without public factor data. It preserves the tensor and identity absorption
when no pruning is needed. Pruned output is only an initialization.

To generate a scratch checkpoint from the pinned baseline:

```sh
uv run python - <<'PY'
from tasks.dfthcsos import factor_pipeline  # set one BLAS thread before NumPy
from pathlib import Path
import numpy as np
from tasks.dfthcsos.factor_support import BASELINE, checked_inputs, write_npz, sha256
from tasks.dfthcsos.factor_reseed import regroup
root = Path('/home/cld-main/work/vqcc-data/starter-kit')
checked_inputs(root)
with np.load(root/BASELINE, allow_pickle=False) as archive:
    params = {k: archive[k] for k in archive.files}
output = Path('/tmp/pra235-regroup-example.npz')  # must not exist
write_npz(output, regroup(params, 6, 144, 127))
print(sha256(output))
PY
```

Real construction probes produced (6,144,127) and (1,496,384), recorded in
`ledger/evidence/pra235/regroup-probe.json`. The integrated two-iteration smoke measurement is also recorded; it misses accuracy
and is a wiring check, not an adequate optimization budget.
The helper raises `ValueError` for nonpositive dimensions, growth in R, or B/C
beyond the available merged basis/SVD rank. It never reads a checkpoint or writes
files itself; the explicit `write_npz` call writes one exclusive archive.

## Fit against rounded vectors

`factor_quantized.refit_quantized(params, target, steps, penalty, quantize,
maxcor=20)` rounds and decodes U once, then holds those vectors fixed while
fitting W with an analytic L-BFGS-B gradient. The explicit `quantize` callback
must use the pinned Google `tree_angles`, `angles_to_words`, and
`words_to_vectors` at the desired bit width. The target is the same packed
fixed-shift integral tensor as in PRA-198. The callback's output must be finite,
normalized, and the same shape as U. Invalid inputs raise `ValueError`.

This fits the actual rounded-vector residual without pretending rounding is
differentiable. It does not optimize discrete angles or guarantee a feasible
point. Run offset refinement and unmodified `evaluate_words` afterwards; enforce
hard accuracy, Lambda, gap and domain checks. Optimizer termination, iteration
count, initial/final objective, and maxcor are returned as evidence. The helper
performs no file, network, circuit, credential or submission operations.

## Verification and remaining work

```sh
uv run pytest tests/test_factor_refit_v2.py -q
```

The exact-merge test independently checks the four-index tensor and one-body
absorption. The gradient test compares to finite differences. Replacing the
weight gradient with zero was observed to fail the gradient test; restoring the
implementation passes. Tests also cover deterministic construction, invalid
shapes, fixed rounded vectors and objective reduction.

Pending: long-fit results; gradual pruning to R=32;
penalty and optimizer variants; further quantized fits; larger-shape measurements at
11/10/9/8 bits; repeatability of new fitted checkpoints; final decisions and
review. Existing method notices remain in `notices/30-dfthcsos.txt`. These new
helpers are own NumPy/SciPy implementations extending the already attributed
PRA-198 normalization, D(w), augmented-SVD and Google-encoder methods; no new
public notebook or factor file was read.

The full suite invokes circuit subprocesses that need the competition module on
its import path. The reproducible check in this worktree is:

```sh
PYTHONPATH=/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation/kickmix uv run pytest -q
uv run python -m ledger.registers check
```

The first plain `uv run pytest` had three subprocess import failures (260 passed,
one skipped). With this explicit pinned module path: **263 passed, 1 skipped**.
No repository dependency, gate or test was bypassed or changed for that rerun.

## First passing floor (quantized weight probe)

The (65,60,30) 12-bit probe passes: error1 3.252195718 mHa,
error2 18.318496686 mHa, Lambda 333.813304464, gap 4.05725366724.
An independent reload through `proxy_submission` also passes. Archive SHA-256:
`574099ebd6800473adce47d524ff484886c1b2782a9195d56ad8c0fa1a3d89ef`.
It was handed to PRA-237 immediately. Re-encoding at 11/10/9/8 bits fails; it
was fitted specifically for 12 bits. Both 100-iteration optimizers reached their
caps. This is verifier acceptance, not optimizer convergence.

Reproduce after creating the `pra235-determinism-01` short-run checkpoint with
the long-fit command above changed to `--steps 20 --bits 12`. The probe verifies
its exact cc7dd377 hash as well as all original Google/competition input hashes:

```sh
PYTHONPATH=. uv run python ledger/evidence/pra235/run_quantized_probe.py \
  --out /home/cld-main/work/vqcc-data/pra235-quantized-probe-02 --dry-run
```

Dry-run output: `pinned_files: 26, fit_bits: 12, steps: 100, maxcor: 20`.
Remove `--dry-run` to fit. Existing output paths fail with exit 2 and
`output exists; choose a new --out directory`. Measured 19 mHa success exits 0;
a completed margin miss exits 3. Output includes raw factors, one encoded archive
per measured bit width, progress, settings/optimizer evidence and the final JSON
report. Only `--out` is written. No circuit generation or upload takes place.
The first probe's core source revision is preserved at local 59d3864; the later
CLI change adds dry-run/explicit output and replaces assertion-based input checks
with unconditional errors. Numerical fitting is unchanged.

## Integrated v2 pipeline

The main `factor_pipeline` now accepts regrouped shapes, independent rounded-U
fits, and optimizer variants. Example (validate first, then remove `--dry-run`):

```sh
uv run python -m tasks.dfthcsos.factor_pipeline \
  --starter /home/cld-main/work/vqcc-data/starter-kit \
  --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation \
  --out /home/cld-main/work/vqcc-data/pra235-public-6-example \
  --shapes 6,144,127 --steps 1000 --maxcor 20 --offset-steps 200 \
  --bits 12 11 10 9 8 --quantize-bits 11 10 9 8 --quantized-steps 500 \
  --checkpoint-every 25 --dry-run
```

`--quantize-bits` must be a subset of measured `--bits`. Each selected width
gets an independent fit from that stage's continuous factors, followed by offset
refinement; it does not inherit a fit trained at another width. The untouched
(65,60,60) control is always measured first. Larger B/C triggers the documented
regrouping initializer; R never grows. Ordinary pruning uses the original method.

`--optimizer lbfgs` remains the default and `--maxcor` selects its memory size.
`--optimizer adam --learning-rate 0.0001` runs the stated fixed number of Adam
updates (beta1=.9, beta2=.999, epsilon=1e-8); it does not claim convergence.
`--optimizer trust-ncg` uses central finite differences of the analytic gradient
for Hessian-vector products, without materializing a dense Hessian. This is an
experimental variant for a nonsmooth D(w) term, not a convergence guarantee.
Diagnostics count all objective/gradient evaluations including Hessian probes.

Every 25 structural iterations by default, an exclusive
`inflight-STAGE-ITERATION.npz` is written with a hash and elapsed time in the
stage's `inflight-STAGE.json`. These are explicitly **unverified**, have not had
final offset refinement, and cannot be handed off. Completed stages and each
finished bit-width evaluation write `progress.json`; every measured point has
its own encoded archive and hash. Existing output is still refused. A source
change during a run remains an error. Run long jobs from a committed source
snapshot rather than the editable worktree.

The v2 exit criterion is now explicit: exit 0 if the last requested shape has a
point with both errors ≤19 mHa and all acceptance checks passing; exit 3 for a
complete miss. `floor_65_met` and `floor_32_met` separately report the specified
12-bit and 10-bit floor points. This supersedes the legacy compressed 2.5x exit
criterion for new runs, while old evidence remains tied to its committed source.
Intermediate or interrupted runs are never a numerical failure verdict.

## Sequential experiment batches

`run_experiments` runs a committed JSON plan with one fixed starter root, one
fixed competition root, and named jobs containing pipeline arguments. Each job
starts from the pinned Google baseline and includes the untouched control.
Use the same WSL Python environment and input prerequisites as the pipeline:

```sh
uv run python -m tasks.dfthcsos.run_experiments --plan ledger/evidence/pra235/plan-floor.json --out /home/cld-main/work/vqcc-data/pra235-batch-floor-01 --dry-run
```

Remove `--dry-run` to execute from a committed source snapshot. The runner writes
only the new output directory: a copy of the plan, `jobs.json`, per-job logs and
pipeline outputs. It invokes the current Python executable without a shell.
It refuses existing output, duplicate/path-like job names, and path overrides.
Exit 2 means invalid input; exit 1 means a job had an operational error (read its
log); exit 0 means all jobs completed, including numerical misses. Scientific
acceptance always comes from each job's report. No job is silently skipped.
The runner does not detach or schedule itself. For multi-heartbeat runs, launch
from the recorded committed snapshot in a separate process session and record
the PID, source commit, plan hash and log paths on the issue. A scheduled issue
monitor must collect results and hand off any passing checkpoint.
