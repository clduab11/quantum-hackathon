# JAX DF-THC loss (PRA-251)

This package evaluates a quantisation-aware DF-THC loss on an accelerator and
checks its five physical terms against the unmodified competition verifier.
This is the loss-review deliverable, before an optimizer or long run. John Wick's
approval on PRA-253 is required before a long fit. The 15-minute >=4x circuit
smoke, shape sweeps and >=6x verified point remain future B1 deliverables.

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
circuit build, remote operation or Kaggle upload in this command. Removing this
package removes only the mirror/loss API; no other tool imports it.

`uv sync` does not install optional GPU packages. Use `--group gpu` for all loss
commands. JAX 0.12.0.1 is pinned with the documented `cuda12` extra, the concrete
CUDA-12 spelling of the brief's `jax[cuda]`. Package wheels are hash-locked in
`uv.lock`. [JAX installation](https://docs.jax.dev/en/latest/installation.html)
and [memory allocation](https://github.com/jax-ml/jax/blob/main/docs/201/gpu-memory.md)
explain the extra and preallocation switch. TPU execution has not been tested; B2 owns that validation. This worktree has its own venv;
preallocation is disabled so it does not reserve 75% of the GPU beside T3.
The gpu group from T3 is not merged into this branch's base yet; the merge gate
must check the shared dependency files before either branch is called ready.

## Loss specification

All loss arrays use float64 (`jax_enable_x64=True`). Trainable parameters are
`angles` (N+RB,N-1), in units of pi; signed `w` (R,B,C); and native identity
`offsets` W (R,C). Both one- and two-body rows have independent Givens angles.
S and beta_1 are fixed: the official `load_inputs` replaces the factor's shifts
with the pinned competition shifts, including the original float32 rounding.
H2_I is recovered as W + sum_b w when a future driver serializes a factor.

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
