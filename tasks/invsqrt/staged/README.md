# PRA-313 staged design gate

**STOP: the modeled schedule does not reach Q ≤ 63 and 18.9×.** This directory
contains a budget, not a candidate generator. No circuit was built or submitted.
The result applies to this port's current coefficients and arithmetic kernels;
it is not an impossibility proof for a new coefficient layout or adder.

Run from the repository root:

```sh
uv run python -m tasks.invsqrt.staged.budget
uv run python -m tasks.invsqrt.staged.budget --require-target
# Optional independent recount from the own fit used by PRA-285:
uv run python -m tasks.invsqrt.staged.budget --fit /path/to/fit.json
```

The second command prints the report and exits **1**, deliberately rejecting the
design. The default report needs no GPU, kickmix, competition data, or cached
fit. The optional fit is analysis evidence, never a declared generator input.

## Evidence and corrections

The baseline is repository commit `05751b83dd73f597faa23be342f60363f3dd9f7e`,
`docs/decisions/D-PRA285-01.md`, `public_port/profile.py`, and the existing
`public_port/{schedule,arithmetic,deferred,virtual_low,model}.py` kernels.
The own fit has SHA-256
`672e4e010f143c8ff5b40b3e2244a7d3ea0cfb990f42d7a52549cb2543893985`.
The profile was retained at `/tmp/pra285/profile-before.json`; its counts are
transcribed into `budget.py` and are independently auditable against the kernels.
The calibrated margin and costs also agree with the retained own build report
`/tmp/pra249-implementation-6AvJmF/final/build-report.json` and
`/tmp/pra285/design1-affine.json`. These temporary paths are evidence locations,
not dependencies of the default model.

The research report's §2–3.3 provides the proposal, not measured savings for our
port. Its incorrect Q90/C1742.8 baseline is not used. Code inspection establishes:

- Our baseline is Q84, 1,553 expected Toffolis, 44 arbitrary rotations and one
  literal T. Margin is 78,847,037 units of 2^-64 turns after calibration.
  C = 1,867.65435487 and estimated ratio = 13.2377293×; the recorded official
  fixed-salt result is 13.237730853850163×.
- Four binary normalization flags already exist. `x[21]` stores the odd-shift
  octave flag (`f[0]`) after the special final normalization step. It is not
  a clean constant in this port. Borrowing it needs a different encoding.
- High K0 is already phased and HMR'd before curvature arithmetic. The useful
  new move is delaying allocation/loading of low K0 until after the inner MAC.
- Curvature is **8** bits and interpolated with a 4-bit step register. Both
  loads together cost 138 Toffolis. The current fit is not constant within
  groups of eight addresses, so the report's 12-Toffoli grouped load cannot
  simply replace it.
- All index-only HMR debts are already merged. `deferred.repair_anf` computes
  11+11 AND monomials with 23 work wires in the valley: **22** Toffolis, Q49.
  Replacing it with a 26–40-Toffoli method is not a saving.
- The materialized high/low phase kernels cost 66+154 = 220 Toffolis, with
  **10** extension wires, not eight. Removing every one of those Toffolis is
  an optimistic bound; any real controlled tap must be charged.

`--fit` re-evaluates all 16,384 residual values per coefficient row with our
integer model, reconstructs the split/anchor layout, and counts ANF DFS nodes
including unprinted ancestors. It yields widths (res, coarse, low, high) =
(12, 7, 20, 8) and lookup AND counts:

| Lookup | ANDs |
|---|---:|
| low | 247 |
| high | 241 |
| derivative | 247 |
| high + derivative | 247 |

## Schedule and allocated ids

The literal A/B/C schedule needs three lookups. A cheaper ordering phases high
before stage A, loading high and derivative together, then loads low separately.
Index-only phases commute with the subsequent arithmetic. This two-lookup
version adds 247 ANDs; the literal ordering adds a further 241.

The table retains existing arithmetic and materialized phase kernels. HMR
releases only index-only words, and derivative arithmetic is reversed coherently.
The low word is HMR'd after the outer inverse, before the inner inverse. The
allocator reuses the smallest free id, retains x/flags throughout, and prints
explicit ids in JSON. High-water is the largest allocated id + 1, never merely
the current live count. Stage-local carry ladders are cleaned at boundaries.

| Stage | Live wires | Id high-water | Expected Toffolis | Rotations |
|---|---:|---:|---:|---:|
| Normalize | 40 | 40 | 104 | 0 |
| High + derivative lookup | 60 | 60 | 247 | 0 |
| Phase high, then HMR | 63 | 63 | 66 | 15 |
| Curvature load | 63 | 63 | 69 | 0 |
| Inner MAC | 63 | 63 | 87 | 0 |
| Coarse carry | 50 | 63 | 6 | 0 |
| Low lookup | 72 | 72 | 247 | 0 |
| Outer MAC | 84 | 84 | 280 | 0 |
| Phase low | 75 | 84 | 154 | 29 |
| Outer inverse | 84 | 84 | 280 | 0 |
| Coarse carry inverse | 50 | 84 | 6 | 0 |
| Curvature reload | 63 | 84 | 69 | 0 |
| Inner inverse | 63 | 84 | 87 | 0 |
| Merged repair | 49 | 84 | 22 | 0 |
| Unnormalize | 40 | 84 | 89 | 0 |

Sum = 1,813 expected Toffolis before a generously retained 13-Toffoli affine
compiler credit from the baseline, leaving 1,800. That credit has not been
re-measured for a new circuit. The unnormalization count includes fair-HMR
discounts (100 static versus 89 expected); conditioned CZ repair is free.

The binding stages are the outer MAC and inverse: x22 + flags4 + res12 + coarse7
+ low20 + carry18 + virtual-carry1 = **84**. Parking all flags, even for free,
still leaves 80; the payload alone is 61. Reaching 63 needs at least 17 of the
19 scratch wires removed or borrowed during these rows. The low lookup also
needs 68 with all flags parked, so at least five of its seven ladder wires
must be eliminated or borrowed. No valid schedule for either is supplied by
the report. The three previously failed parking designs were not retried.

## Cost gate and deliberately favorable bounds

Pricing follows `tasks/invsqrt/calibrate.py`: epsilon = pi × margin / 2^64 / Nrot;
T per rotation = 0.56 log2(1/epsilon) + 5.3; C = mean Toffolis +
(literal T + Nrot × T per rotation)/4. The rotation surcharge is 314.65435487.
The margin is a **global** minimum, repeated in each stage record for clarity,
not independent stage margins that can be added. It transfers only if phase
activations remain exact. No truncation or rotation removal is assumed.

| Model | Q | Mean Toffolis | C | Estimated ratio |
|---|---:|---:|---:|---:|
| Existing verified baseline | 84 | 1,553 | 1,867.6544 | 13.23773× |
| Two-lookup staged schedule, existing kernels | 84 | 1,800 | 2,114.6544 | 11.69151× |
| Grant entirely free phase taps | 84 | 1,580 | 1,894.6544 | 13.04908× |
| Also grant Q63 and two 12-Toffoli curvature loads | 63 | 1,466 | 1,780.6544 | **18.51267×** |

The final row is an optimistic conditional bound, **not a feasible candidate**.
It grants all area reductions, flag restoration and phase selection for free,
retains the cheaper existing phaseup, and grants the full compiler credit.
At Q63 the target requires C ≤ **1,744.16245378**, leaving at least **36.4919**
additional Toffoli-equivalents to save even under these assumptions. Real tap,
parking or low-workspace lookup costs increase that deficit. A changed fitter,
adder, table compiler or improved margin could change this conclusion and needs
a new budget; this model does not rule those out.

No new circuit SHA-256, official 200,540,928-shot verification, or clean-clone G5
result exists: implementation is stopped at the issue's design gate. Existing
Apache-2.0 parent attribution remains in `tasks/invsqrt/PROVENANCE.md`, the ledger,
and `notices/10-invsqrt.txt`. No unlicensed external code was used or copied.
