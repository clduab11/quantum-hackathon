# Google-baseline factor refit

`factor_pipeline.py` runs a deterministic CPU rank/precision sweep from the
SHA-256-pinned Google (65,60,60) baseline. It writes factors and numerical
evidence, not circuits or a Kaggle submission ZIP.

## Run

From this repository in WSL, run `uv sync`. The downloaded starter-kit **v4**
must be at the named starter root, with the original relative paths. The
competition root must contain `verifiers/dfthcsos/` and `kickmix/kickmix.so`.
No credentials, global installation, JAX, PyTorch or GPU are required.

```sh
uv run python -m tasks.dfthcsos.factor_pipeline \
  --starter /home/cld-main/work/vqcc-data/starter-kit \
  --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation \
  --out /home/cld-main/work/vqcc-data/my-factor-sweep \
  --steps 200 --offset-steps 200 --dry-run
```

Remove `--dry-run` to run. Each run needs a new output directory. For a short
experiment use `--steps 20 --offset-steps 100`. For a narrower run use
`--shapes 65,60,30 --bits 12`. The full default schedule is
(65,60,60) as a control, then (65,60,30), (55,60,30), (48,60,30),
(42,60,30), (36,60,30), (32,60,30), (32,32,30); bits 7 through 12.
Increase iterations for longer refits; a short floor miss does not establish
that a shape is infeasible. R must not grow. The v2 regrouping initializer permits
larger B/C within the available merged rank; see [REFIT_V2.md](REFIT_V2.md).

The public archive endpoint returned 404 during acquisition. Individual files
worked without credentials, using each `url` in `ledger/manifests/inputs/pra198-google-v4.json`. The
manifest records the source version, licence, paths, sizes and hashes. The
pipeline does not download data or silently substitute another baseline.
It checks all input hashes before importing third-party Python.

## Method and limits

The two-electron target is built from the original integrals plus the fixed
symmetry shift, in an orthonormal symmetric-pair basis. The structural objective
is its full Frobenius residual plus
`2e-5 * D(w)`, where `D(w) = 0.5 sum_rc[(sum_b |w|)^2 - (sum_b w)^2]`.
Analytic gradients include row normalization. SciPy L-BFGS-B uses float64,
`maxcor=5`, `ftol=1e-12`, `gtol=1e-8`, `maxls=20`. Intermediate iterates may
violate accuracy; only independently evaluated final points can pass.

Groups are ranked by the squared Frobenius norm of their X tensors; bases by
squared weight norm. A stable sort breaks ties. Reducing C uses an SVD of
`[W; H2_I]` with a fixed column-sign convention. Every cut is followed by a
structural refit. The identity offsets are then refined against lambda_eff,
with soft penalties at the Lambda and gap floors (`maxls=30`). `H1_I` and
`Hsym_lower` remain the verifier's fixed values throughout. A penalty or an
optimizer success flag never substitutes for the verifier's strict gates.

Google's pinned encoder uses nearest rounding on its log-depth Givens tree,
then rebuilds the one-body eigenvectors from the decoded two-body vectors.
Every row is measured with the unmodified competition `evaluate_words`.
Optional v2 fits hold decoded vectors fixed at each requested bit width and
refit weights and offsets. Gram-gauge optimization is not implemented. The run reports optimizer termination, including iteration
limits; it does not relabel those as convergence.

**Cost is a conservative ordinary-QROM prediction.** The package's
`heuristic_costs` covers inner/outer preparation and Givens rotations only.
We add `2*(N+R*B-2)*ceil((N-1)/J)` lookup Toffolis, with J at most 8 and
register width at most 128 qubits. Q combines persistent registers and the
maximum sequential temporary workspace, as the verifier does. This model
reproduces reference T=93,237 and Q=730. It can overcount constant lookup
subtrees. It does **not** claim the public banked/six-wire QROM cost, and
P1-2b must measure any proposed circuit implementation. Public 2.81x values
are comparison rows, not our measurements.

## Outputs and failure behavior

`rank-curve.json` includes each measured point, settings, runtimes, input pins,
optimizer diagnostics and checkpoint hashes. `rank-curve.md` is the table;
`progress.json` preserves completed stages. `factors-NN.npz` are deterministic
checkpoints. The best point passing the numerical gates is written to
`submission.npz` with U, W, H2_I, H1_I, Hsym_lower, tree_edges, angle_words and
an explicit scalar `brot`. G2 reads `brot`; historical archives default to 12.
All decoded arrays together must be at most 64 MiB. The filename does not
authorize shipping: this task produces no ANGLE circuits and has no G3/G5 or
candidate-specific shipping sign-off. A control-only winner is not a P1-2b
performance candidate.

Exit **0** means a dry run passed or the final requested shape has a point with
both errors at most 19 mHa and all numerical acceptance checks passing (PRA-235).
This replaces the original PRA-198 compressed 2.5x exit criterion for new runs. Exit **3** means a complete measured sweep missed the floor; inspect the
curve and failed constraints. Exit **1** means an input, write or numerical
error; stderr identifies the problem. Existing runs are never overwritten.
An interrupted run is partial evidence and must not be called complete.

Only the specified output directory is written. No subprocesses, network
calls, circuits, salts, submissions or live services are involved. BLAS thread
counts are set to one before import. No random seed or checkpoint is selected.
Repeated runs in the same pinned Python/NumPy/SciPy/CPU environment must match
checkpoint/NPZ hashes; timestamps, paths and runtimes are expected to differ.
Cross-platform bit equality is not claimed.

## Provenance map

| Module | Code/input parent |
|---|---|
| `factor_math.py` | Own analytic NumPy implementation; D(w) and group-importance method credited to Ahmed Berat Ozer, Group Compression v1 (PRA-194 evidence) and inspected v2 `src/dfthc_train.py`, Apache-2.0. No tensor or checkpoint from that notebook is loaded. |
| `factor_offsets.py` | Own analytic offset gradient using Google's fixed-shift equations; effective-norm method context from Ozer v2, crediting Kozykappa and anazemcev. No Gram gauge is ported. |
| `factor_pipeline.py` | Own orchestration; imports Google's v4 encoder/tree and competition verifier, pinned in the manifest. |
| `factor_support.py` | Own I/O and upper-bound accounting; ordinary-QROM construction already ported in `generate.py` from the Apache-2.0 competition package. No banked/six-wire circuit code is ported. |
| `ledger/manifests/inputs/pra198-google-v4.json` | Third-party data and source pins; Google baseline/integrals/fixed shift are input parents, distinct from method-code parents. |

Notices are in `notices/30-dfthcsos.txt`. The original Google/source files stay
unchanged in the downloaded input tree with their file-specific notices.
The inspected notebook source hash is recorded in the ledger input manifest.
All k256-derived factors, words, coefficients, targets and checkpoints remain
excluded from initialization and fitting.

## Verification

`uv run pytest tests/test_factor_pipeline.py` checks analytic gradients against
independent finite differences, tensor packing, compression, cost accounting,
declared precision, input refusal and deterministic exclusive archive output.
`uv sync`, `uv run pytest`, `uv run python -m ledger.registers check`, and
`uv run python scripts/merge_gate.py --ref mine=HEAD` are the branch gates.
Real-input results and rerun hashes are recorded in PRA-198's `rank-curve` and
`verify-log` documents. No wrapper result replaces those measured records.
