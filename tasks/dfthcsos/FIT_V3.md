# Public-method feasibility fit from Google

`factor_fit_v3` measures balanced SOMP/PSD group merging, structural training
and tangent Gauss–Newton on Google's pinned baseline. It writes exclusive
factor checkpoints and independently evaluated rounding diagnostics.

## Run and prerequisites

Run `uv sync` in this repository under WSL. Obtain the Google starter v4 and
competition inputs named in `ledger/manifests/inputs/pra198-google-v4.json`.
All hashes are checked before importing the package's encoder or evaluator.
No downloads, credentials, GPU, external checkpoints or input discovery occur.

```sh
uv run python -m tasks.dfthcsos.factor_fit_v3 \
  --starter /home/cld-main/work/vqcc-data/starter-kit \
  --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation \
  --out /home/cld-main/work/vqcc-data/pra242-r6-v3 --shape r6 --dry-run
```

Remove `--dry-run` for the numerical run. Use `--shape thc` and a new output
directory for (1,496,384), after the (6,144,127) run. There is no resume option:
only the pinned Google baseline can enter the driver. Existing output paths
are refused. Only `--out` is written; the process invokes no subprocess or
service. Deleting a run is unnecessary to retry: select a new output path.

Default work limits are 8 PSD sweeps, 500 structural L-BFGS iterations,
30 tangent Gauss–Newton iterations with at most 30 PCG iterations each,
and 400 identity-offset iterations. Two BLAS threads, float64 throughout.
No random initializer or stochastic probe is used (seed is null); the test
fixtures use seeds 95101 and 78. Optimizer convergence/line-search conditions,
the source GN 15 mHa target and exhausted damping can terminate a stage early.
Actual iterations, function evaluations and CG counts are recorded. Wall time
is recorded only as evidence and never controls a stop.

## Method boundary

This is an initializer substitution and bounded CPU adaptation, **not an
exact replay** of either public team's result. `run_gpu_qat.py` actually starts
its merge branch at (6,157,127), then uses adaptive Schur projector deletion
for the B144 continuation. This experiment starts directly at (6,144,127)
and does not reproduce that B157-to-B144 curriculum. The source permits
8000 outer Torch L-BFGS steps (up to 5 inner iterations each), 700 seconds,
then up to 300 GN iterations with 100 CG steps and 450 seconds. Our schedule
is smaller and hardware-independent. SciPy L-BFGS-B without bounds replaces
Torch L-BFGS, retains history 20, and minimizes the same
`1000*(full packed Frobenius residual + 2e-6*D(w))`, with row normalization.
Its line search and termination rules differ; no convergence equivalence is
claimed. The structural stage returns the final objective iterate, rather
than selecting the lowest residual among the source's periodic snapshots.
Canonical eigenvector signs remove a gratuitous initialization gauge; the
PSD eigenvalue floor is 1e-14 (source initialization: 1e-12, sweeps: 1e-14).
Unlike the public loader, no Ahmed, k256 or other public factor is an input.

The source's balanced similarity merge keeps all parent groups, SOMP selects
a shared projector dictionary, and full-target PSD block coordinate descent
refits its core. Rank-deficient dictionaries fail explicitly. The GN stage
uses the source's analytic tangent JVP/VJP, normal operator, diagonal PCG,
damping and backtracking sequence. It minimizes the physical residual only.

The source driver skips lattice training above 30 mHa. When that gate fails,
this tool records a continuous-stage negative result. Progressive angle
freezing/importance probes, fixed-word QR refit, gauge rotation, joint error/
gap/Lambda barrier and one-body word polishing are **not reproduced** by this
bounded feasibility tool. If the continuous result reaches 30 mHa and the
rounded diagnostics fail the task floor, exit 4 explicitly requires that
continuation; it is not a complete negative result. No Gluzdov training
reproduction is claimed: his public v14 does not publish its training optimizer.

For independent diagnostics, the existing offset optimizer then minimizes
lambda_eff with soft floors at Lambda=49.0001 and gap=3.915, both strictly
above the verifier limits. These margins are not acceptance guarantees.
The unmodified competition `evaluate_words` measures the resulting factors
at 10, 11 and 12 bits with Google's encoder, including one-body re-encoding.
Both errors must be at most 19.5 mHa, Lambda strictly above 49.0 and gap
strictly above 3.914898. A finite positive lambda_eff and predicted ratio
at least 3.0 are also required. The prediction includes the existing ordinary
ANGLE-QROM term, not a claimed ANF circuit implementation. Target is 3.8x.

## Evidence and exits

`progress.json` persists completed stages; `report.json` marks a completed
run. Stage NPZ and `inflight-*.npz` files use PRA-235's exclusive deterministic
writer and callback. Reports include package and source hashes, settings,
versions, completed work, full metrics, T/Q/ratio, and checkpoint hashes.
`rounded-diagnostic-b*.npz` also contains the exact encoded words and width.
Nothing here is a circuit-verifier pass or a submission authorization.
An interrupted run without `report.json` is partial evidence.

Exit 0 means the measured floor passed or a dry run succeeded; 3 means a
complete bounded run missed the continuous 30 mHa gate and the measured
floor; 4 means quantisation continuation is needed; 1 means invalid input,
unavailable rank, changed source or numerical/I/O failure. Errors go to stderr
and identify the next corrective action. A bounded miss does not prove a
shape or a public method infeasible.

Check with `uv run pytest tests/test_factor_fit_v3.py`. Tests compare GN
derivatives to independent dense forms, preserve all groups in exact-rank
merges, check deterministic PSD reduction and reject invalid ranks and
each failing floor. Repository-wide requirements remain `uv sync`,
`uv run pytest`, `uv run python -m ledger.registers check`, and the merge gate.
As documented in REFIT_V2.md, the circuit subprocess tests require the pinned
kickmix directory on `PYTHONPATH`:

```sh
PYTHONPATH=/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation/kickmix uv run pytest
uv run python ledger/evidence/pra242/check_acceptance.py
uv run python ledger/evidence/pra242/check_acceptance.py --negative
uv run python ledger/evidence/pra242/check_source_parity.py /tmp/pra242-provenance
```

The negative acceptance fixture deliberately exits 1 after removing the
error1 margin check **in memory**. The source parity fixture needs the reviewed
source archive extracted at its explicit argument, verifies the two source
hashes, and executes only isolated math definitions on synthetic arrays.
Both fixtures write nothing. Their `--help` text describes prerequisites and
failure behavior. Parent identities and licences are recorded in
`ledger/evidence/pra242/method-parents.json`.

To audit the serialized factors independently of the fitting process, run:

```sh
uv run python ledger/evidence/pra242/recheck_words.py \
  --starter /home/cld-main/work/vqcc-data/starter-kit \
  --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation \
  --data-root /home/cld-main/work/vqcc-data
```

This read-only check verifies package and checkpoint hashes, loads each of the
six encoded files through the official `load_inputs`, and compares the five
physical metrics to its committed report. A corrupt file fails before loading.
The run directories and report JSONs must already exist; it writes no files.

## Measured outcome

Both bounded runs missed the floor. Final continuous errors were 86.796484 mHa
for (6,144,127) and 35.160044 mHa for (1,496,384). Their best rounded error2
values were 87.709208 and 38.568975 mHa, both at 12 bits. All six points fail
error2 and the modelled 3x ratio. The single-group run is close to the source's
30 mHa gate but has not crossed it; longer training remains untested.

The [result table](../../ledger/evidence/pra242/results.md), per-shape reports,
130 checkpoint hashes, and D-PRA242-02 through D-PRA242-09 record the limits
and every measured negative. No passing integration candidate is produced.

## Module provenance map

All new modules are Praxen reimplementations under Apache-2.0. Source-only
evidence, exact notebook URLs/hashes/licence cells, and the reviewed input
substitution are in PRA-242's `fit-v3-report` and source evidence archive
SHA-256 `8bd6da377b1509aff1c03ae9c5bd77d567d646ec46e834a85283af394b0ac692`.

| Module | Method parent and boundary |
|---|---|
| `factor_merge.py` | anazemcev / Artem1410 / ViberTeam v6, `merge_initialize.py` and `structural_train.py`: similarity merge, SOMP and PSD refit; Google initializer replaces Ahmed R26 |
| `factor_gauss_newton.py` | same source bundle, `gauss_newton.py`: tangent geometry, PCG and damping, reimplemented in NumPy |
| `factor_fit_v3.py` | same bundle, `structural_train.py` and `run_gpu_qat.py`: structural loss and stage ordering; uses existing PRA-198 analytic gradient, replaces optimizer and fixed work budget |
| `factor_measure.py` | own acceptance wrapper around hash-pinned Google encoder/evaluator and existing PRA-198 ordinary-QROM prediction |
| `factor_offsets.py` (unchanged) | PRA-198 identity-offset refinement, reused for diagnostics; not a reproduction of the source joint barrier |
| `(1,496,384)` shape | Dmitrii Gluzdov v14, shape/description only; our method at this shape, no published optimizer to reproduce |

Notebook identities: anazemcev v6, *Quantum Circuits — 881Q Paired DQI + R6
DF-THC*, https://www.kaggle.com/code/anazemcev/quantum-circuits-881q-paired-dqi-r6-df-thc,
SHA-256 `d4a147523ac07cb2dc5fe4bd5dc9c7da48719e34dfc847402628723b37930682`;
Dmitrii Gluzdov v14, *Quantum Circuit Compilation from Source*,
https://www.kaggle.com/code/dmitriigluzdov/quantum-circuit-compilation-from-source,
SHA-256 `c3ba0bdde177b5fa159fc641d065c08870020fd773fa0947675675101eb2f52a`.
Both declare Apache-2.0 in their inspected source. The R6 rebuild source is
the hash-manifest-checked ViberTeam dataset v2 (24 source files), also
Apache-2.0. Its inherited attribution names Ahmed Beratozer for structural
group compression and quantisation, and Kozykorpesh / Sumit Chongder /
Kirill Tym / Artem1410 for the compiler lineage. No compiler or loader is
copied here; no upstream numerical data is fetched or loaded.
