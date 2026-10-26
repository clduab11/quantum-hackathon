# JAX DF-THC loss (PRA-251)

This package evaluates a quantisation-aware DF-THC loss on an accelerator and
checks its five physical terms against the unmodified competition verifier.
John Wick approved the loss at remote revision `6805eb9` on PRA-253. The driver
adds guarded Adam steps and exact export without changing the approved angle,
assignment or loss modules. Shape sweeps and the >=6x verified point remain
outstanding; recorded smoke results are separate from that floor.

## Run the mirror

Requires Python 3.13, WSL CUDA GPU (or a JAX TPU installation), and the declared
public factor plus both hash-pinned packages. No CPU fitting fallback. Run in
this task's separate worktree, never in another running job's environment:

```sh
uv sync --group gpu
XLA_PYTHON_CLIENT_PREALLOCATE=false OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 \
uv run --group gpu python -m tasks.dfthcsos.fit_jax.mirror \
  --starter /home/cld-main/work/vqcc-data/starter-kit \
  --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation \
  --factor /home/cld-main/work/vqcc-data/inputs/thc/femoco_thc_r5.npz
```

The command prints JSON and writes no files. It refuses a missing accelerator,
changed source/input hash or absolute disagreement greater than 1e-10 with a
nonzero exit and a diagnostic on stderr. Repeated runs use the same inputs;
wall-clock timing can vary. There is no seed search, optimizer step, checkpoint,
circuit build, remote operation or Kaggle upload in this command. The driver in this
package also imports the loss API; no external tool depends on this package.

`uv sync` does not install optional GPU packages. Use `--group gpu` for all loss
commands. JAX 0.12.0.1 is pinned with the documented `cuda12` extra, the concrete
CUDA-12 spelling of the brief's `jax[cuda]`. Package wheels are hash-locked in
`uv.lock`. [JAX installation](https://docs.jax.dev/en/latest/installation.html)
and [memory allocation](https://github.com/jax-ml/jax/blob/main/docs/201/gpu-memory.md)
explain the extra and preallocation switch. TPU execution has not been tested; B2 owns that validation. This worktree has its own venv;
preallocation is disabled so it does not reserve 75% of the GPU beside T3.
The optional gpu group now includes the pinned T3 PyTorch runtime. Ten shared
NVIDIA versions differ from the measured JAX run04 environment. See
[the dependency reconciliation and historical replay instructions](../../../docs/PRA260-DEPENDENCIES.md).
Historical scores remain tied to their recorded environment. This candidate
requires scoped review and a passing full merge-order gate before readiness.

## Loss specification

All loss arrays use float64 (`jax_enable_x64=True`). Trainable parameters are
`angles` (N+RB,N-1), in units of pi; signed `w` (R,B,C); and native identity
`offsets` W (R,C). Both one- and two-body rows have independent Givens angles.
S and beta_1 are fixed: the official `load_inputs` replaces the factor's shifts
with the pinned competition shifts, including the original float32 rounding.
H2_I is recovered as W + sum_b w when the driver serializes a factor.

For precision k in {12,11,8}, each forward evaluation uses

```
m = floor((angle mod 2) * 2**(k-1) + 1/2) mod 2**k
rounded_angle = m / 2**(k-1)
```

This is half-up, not nearest-even. Ordered tree rotations act on e0. Rows are
normalized, split, then the two-body rows are normalized again as in the verifier.
`quantize` has a custom identity JVP: its forward value is exactly rounded, but
its tangent is a straight-through surrogate. This is a training heuristic,
not the mathematical derivative of the piecewise constant forward function.
See [JAX custom derivatives](https://github.com/jax-ml/jax/blob/main/docs/301/cookbook.md).

The terms follow `verifiers/dfthcsos/scoreinfra/dfthc_math.py`:

```
X_rcpq = sum_b w_rbc u_rbp u_rbq           (symmetrize from lower triangle)
h = H1_THC - electrons*S/2 + beta_1*I - sum_rc W_rc X_rc
lambda, V = eigh(h)
match = argmax_permutation sum_j abs(v_j @ V[:, match[j]])
error_1 = norm(sum_j lambda[match[j]] v_j v_j.T - h, 'fro')
error_2 = norm(sum_rc X_rc tensor X_rc - tei - (S tensor I + I tensor S)/2, 'fro')
Lambda = sum_j abs(lambda_j) + sum_rc (sum_b abs(w_rbc) + abs(W_rc+sum_b w_rbc))**2/4
E_SOS = ecore - electrons*beta_1 - (sum_j abs(lambda_j)-sum_j lambda_j) - sum_rc W_rc**2/2
E_gap = energy_upper - E_SOS
```

The matching uses device-side shortest augmenting paths, not greedy row choices
or an identity assumption. Its permutation is discrete, with no tangent. The
loss differentiates matched eigenvalues, not eigenvectors through matching.
At exact overlap ties the first minimum column wins; the optimum permutation
need not be unique. Exact eigenvalue degeneracies remain nonsmooth for fitting.
Tests compare assignment objectives with SciPy, include a greedy counterexample,
and reverse public one-body rows without changing any physical terms.

The two-body residual uses `factor_math.packed_target`: lower-triangle entries
weighted by 1 on diagonal and sqrt(2) off diagonal. This preserves the full
N**4 Frobenius norm for the symmetric FCIDUMP tensor and avoids allocating that
full residual. It does not use subtractive Gram-norm identities. The official
numpy full tensor remains the independent oracle.

The separate training objective is

```
sqrt(max(E_gap*(2*Lambda-E_gap), 1e-20)) + 1e6 * sum(max(violation,0)**2)
violations = [error_1-.0195, error_2-.0195,
              49.0001-Lambda, 3.915-E_gap, E_gap-2*Lambda+.0001]
```

The margin targets intentionally exceed the strict acceptance floors. A finite
penalty cannot guarantee feasibility: `Lambda <=49.0`, `E_gap <=3.914898`, either
error >.020, or invalid domain still fails the official verifier. The radicand
extension is only in the training objective. It never clamps reported metrics.
The official Decimal cancellation check, lambda_eff, acceptance and final circuit
score remain with the unmodified verifier and `search/evaluator.py` cascade.

## Tests and review evidence

```sh
VQCC_STARTER=/home/cld-main/work/vqcc-data/starter-kit \
VQCC_COMPETITION=/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation \
VQCC_PUBLIC_FACTOR=/home/cld-main/work/vqcc-data/inputs/thc/femoco_thc_r5.npz \
XLA_PYTHON_CLIENT_PREALLOCATE=false OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 \
uv run --group gpu pytest -q tests/test_fit_jax.py
```

Without JAX or an accelerator these tests skip explicitly. Without the three
input variables only the public integration test skips. The CLI always fails
on missing accelerator; it never silently skips. The suite checks tie rounding,
negative/modulo angles, decoding, optimal matching, floor penalties, independent
finite differences for weight/offset derivatives and deliberately broken mirrors.
The public mirror freshly calls the pinned encoder at each width, then compares
the identical words on GPU and official numpy. It also evaluates one real-data
surrogate gradient without taking an optimization step.

The source public factor is Gluzdov v8, SHA-256
`809a992900937425f01a0593803921873f7bb472d590592c378d3ceb23657df5`.
It is a declared non-circuit input under D-PRA211-05. Full source/package pins,
measured terms, device, timings and maximum absolute differences are in
`ledger/evidence/pra251/mirror.json`. These are numerical mirror points, not
verified circuit ratios or a successful 8-bit fit.

## Reviewer checklist additions

The mirror also checks the factor's **verbatim stored 11-bit words**, separately
from fresh encoder words. It perturbs submitted H1_I by 123 and every Hsym_lower
entry by 17, passes the changed mapping through the same `physics` intake, and
requires identical fixed inputs and JAX terms. GPU placement is asserted for
every parameter, fixed input and tree array. Both code and reference use the
fixed package shifts even when the factor tries to supply different ones.

`admissible` is a conservative proposed-step guard: either error above 20 mHa,
Lambda <=49, E_gap <=3.914898, nonfinite metrics or E_gap >=2*Lambda returns false.
The driver rejects/reverts such a proposed step, including its Adam moments,
before promoting it.
It is not an official acceptance replacement. The official floating-point
upper-domain check is inclusive (`E_gap <=2*Lambda`), followed by the Decimal
check; this guard deliberately rejects the boundary. The test crosses Lambda
from 49.01 to 49.0 and 48.99 and observes rejection.

A continuous internal vector kernel exists to test gradients. At a rounded
angle point, the STE gradient must equal that continuous kernel's gradient and
its directional finite difference. The public `terms` entry always quantizes.
The numerical mirror meets **absolute 1e-10** on every term, including E_SOS
and E_gap; no relative tolerance is used to hide large-energy differences.

## Run the GPU smoke

The fitter needs the same pinned inputs as the mirror. The evaluator subprocess
also needs the local verifier import paths, installed in this worktree's venv:

```sh
uv run python scripts/install_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 uv run --group gpu python -m tasks.dfthcsos.fit_jax.run \
  --starter /home/cld-main/work/vqcc-data/starter-kit \
  --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation \
  --factor /home/cld-main/work/vqcc-data/inputs/thc/femoco_thc_r5.npz \
  --out /home/cld-main/work/vqcc-data/pra251-smoke-example --dry-run
```

Remove `--dry-run` to execute. The output directory must not exist. Defaults are
11 bits, 32 steps, 300 seconds of fitting, Adam rate 1e-4. The fit budget includes
JIT compilation but stops between steps, so one step can overrun it. The measured
900-second smoke limit includes intake, fitting, export, circuit generation and
the official two-shot/64-shot cascade. Compilation is not hidden from this limit.
The CLI exits 0 only if at least one step is accepted, stage 3 passes, ratio >=4,
and the entire run takes <=900 seconds. A negative result exits 1 with evidence
in `report.json`; intake/export errors print a diagnostic on stderr and exit 1.

This command is deterministic (recorded seed 251, no random draws or salt search).
Adam scales each gradient component by its running RMS. Every proposed step is
hard-rounded, must pass `admissible`, and must strictly improve the training
objective. A line search halves the rate up to 40 times. Rejection keeps both
parameters and moments unchanged. If there is accumulated momentum, the driver
tries one fresh Adam direction with the same hard guard; failed restart ends the
fit. Only an accepted restart replaces the optimizer state. Repeating an identical
rejected direction would do nothing. The start itself must be feasible: direct 8-bit rounding of
the public factor is rejected. This driver does not claim an 8-bit recovery fit.

`steps.jsonl` records every trial rate, admissibility, objective, first-step
norms, accepted metrics and assignment time. Assignment timing uses the real
current overlap matrix, synchronizes the device, and excludes compilation and
an explicit warm-up call. It is a separate profiling call, so profiling overhead
is included in total wall-clock but not in the assignment sample. All checkpoints
use `factor_progress.py` and exclusive deterministic NPZ writes. `factor.npz`
contains exact `quantize(angles)` words for **all** N+RB rows. It never regenerates
one-body angles. The exported factor is independently checked with the official
numpy terms before the circuit cascade. Checkpoints are unverified intermediates;
only the final cascade can establish a circuit ratio.

The ANF builder reuses `qrom.py` with eight scratch qubits and degree-four
pebbling. Batch size is the largest that fits the 128-qubit cap at the current
row count and precision (J=10 for this 11-bit start). It does not change words.
The existing evaluator alone determines verified cost and ratio. Its scratch
root and logs live inside the new output directory, so its stale-output cleanup
cannot touch another job's files. No remote system or Kaggle is invoked.

For a regression run, add `VQCC_RUN_JAX_SMOKE=1` to the three input variables in
the test example and run `uv run --group gpu pytest -q tests/test_fit_jax_driver.py`.
The smoke otherwise skips; rollback, export and checkpoint checks still run on
GPU. To remove the local verifier path installation, run:
`uv run python scripts/uninstall_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation`.
Removing this package affects only its mirror, driver and tests; exported factors
and evidence remain readable independently. Outputs are exclusive, so rerunning
requires a new directory rather than silently replacing a previous experiment.

## Probe smaller shapes without promotion

`python -m tasks.dfthcsos.fit_jax.probe_shapes` uses the same three input flags as
the mirror plus repeated `--shape R,B,C` flags. For example, append
`--shape 1,496,383 --shape 1,495,384` to test one fewer ensemble column or basis.
It prints read-only JSON and exits 1 if all proposals fail `admissible`. A feasible
proposal is only an initialization finding, never a circuit score.

The GPU reducer keeps groups/bases with greatest squared weight norm, in their
original order. It truncates a GPU SVD of augmented `[w; offsets]` for smaller C;
singular-vector signs use the first largest-magnitude component. It preserves
the submitted free one-body angles and each retained two-body row. SVD rotation
can raise Lambda despite preserving the untruncated physical tensor; this is a
proposal heuristic, not a guaranteed cost improvement. Each proposal at 12/11/8
bits is compared against official numpy terms with absolute tolerance 1e-10.
The 12-bit probe embeds the stored 11-bit angles exactly; it does not re-encode
one-body vectors. Infeasible proposals are never fitted, checkpointed or promoted.
No CPU fit or CPU SVD fallback exists.

## Bounded continuation result

Run04 (`--fit-seconds 720 --steps 512`) completed on RTX 4060 Ti with 248 accepted
steps. The unchanged official cascade passed at 4.149426342x in 786.344 seconds;
this remains below the 6x floor and is not a score improvement. No angle words
changed; maximum weight change was 9.712e-9. Thus a low step rate can satisfy the
smoke while making negligible progress on the intended quantization problem.
Do not interpret accepted-step count as optimization success. D-PRA251-04 and
`ledger/evidence/pra251/long-04-result.json` preserve this negative result.

No B1 fit remains active. The specified second `(10,129,60)` public factor was
not found in the declared handoff; PRA-258 asks John Wick for its path, hash and
source record or a documented correction. The tested reducer cannot initialize
a feasible smaller factor from the existing start (D-PRA251-03). A new feasible
initialization or a separately reviewed change of fitting policy is needed;
these bounded failures do not establish that smaller optimized factors are
impossible. The loss review conditions remain in force.
