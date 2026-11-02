# VQCC field guide (augmented)

A plain-English guide to the Kaggle competition **Google Quantum AI – Verifiable Quantum Circuit Compilation**
and to how this repository plays it. It is a synthesis, not a copy: the competition facts below were re-read from
the public Kaggle overview, evaluation, timeline and prizes pages on 2026-11-02; the task-specific numbers come
from this repository (`tasks/*/README.md`, `harness/costs.py`, `ledger/standing.yaml`, the decision register);
the playbook ideas were adapted from an independent CC BY 4.0 English field guide (itself an adaptation of
Hidemasa Tsukano's Japanese primer, v1.0, 2 November 2026) and corrected where it disagreed with the official
pages or with what we have measured. Section 10 lists those corrections. Anything that can change (dates, rules,
metric code, file formats) must be re-checked on Kaggle before an upload.

## 1. What the contest is

This is not a machine-learning prediction contest. It is a compiler and numerical-optimisation contest whose
contract is an executable verifier. You hand in three task entries (`invsqrt` and `dqi` are one `kickmix`
circuit each; `dfthcsos` is a bundle of `angle_k_<i>` circuits plus `submission.npz`); Google's simulator runs
every circuit on classical inputs, checks the outputs, the scratch qubits and the phase, prices the circuit, and divides the
reference cost by yours. The loop is: propose a change, regenerate the circuit, verify it, measure its cost, keep
it only if the verified cost went down.

The three tasks are bottleneck subroutines of future fault-tolerant algorithms:

| Task | Science | Subroutine we compress |
| --- | --- | --- |
| `invsqrt` | Stopping power in inertial-confinement fusion fuel | Phase `\|x⟩` by `β/√x` for every x in a 22-qubit register |
| `dqi` | Decoded Quantum Interferometry for Optimal Polynomial Intersection | A reversible Reed–Solomon RS(4095, 4025, 71) syndrome decoder over GF(2¹²) |
| `dfthcsos` | Phase estimation on the FeMoCo Hamiltonian (nitrogen fixation) | The tensor factorisation, Givens tree and QROM lookups that load the Hamiltonian |

## 2. Score and cost model

The leaderboard score is the geometric mean of the three improvement ratios:

```
score = ( Π_task  reference_cost / your_cost )^(1/3)
```

The unchanged reference scores 1.0. Each task prices a circuit differently (`harness/costs.py` mirrors these):

| Task | Cost (lower is better) | Notes |
| --- | --- | --- |
| `invsqrt` | `Q × (Toffoli + T/4)` | Rotations are priced in T; our harness charges about `0.56·log₂(1/ε) + 5.3` T per rotation. Reference: Q 260, 7,735 Toffolis, 37 rotations → 2,076,774. |
| `dqi` | `R(ε⁺) × Q² × Toffoli` with `R(ε) = ln 2 / (−ln(½ + 2√ε))` | ε⁺ is a one-sided Clopper–Pearson upper bound on the decoder's failure rate at δ = 2⁻¹²⁸, about 88.7/N with zero failures, so the zero-failure floor is R ≈ 1.191. **Q is squared.** Reference: Q 1,893, 5,725,461 Toffolis → about 2.44 × 10¹³. |
| `dfthcsos` | `λ_eff × Toffoli × Q` with `λ_eff = √(E_gap (2Λ − E_gap))` | T and Q cover the **whole block encoding**, not only the submitted ANGLE circuits; the state preparation and Givens rotations are priced analytically. Reference: (R, B, C) = (65, 60, 60), 10 circuits, Λ ≈ 308, λ_eff 49.3 → 3,355,599,588. |

Q is the logical-qubit count and Toffoli the Toffoli count, both per shot.

**What this means for strategy**

- Optimise percentage reduction, not raw gate counts. Halving one task multiplies the score by 2^(1/3) ≈ 1.26;
  so does cutting all three by about 20.6 % each. The cheapest percentage wins regardless of absolute cost.
- For `invsqrt` a 1 % saving in qubits and a 1 % saving in Toffoli-equivalents are worth the same. Trading one
  qubit for gates breaks even at roughly C/Q Toffoli-equivalents (about 100 at Q = 100, C = 10,000).
- For `dqi` a 1 % saving in qubits is worth about 2 % because Q is squared. Workspace discipline (register
  liveness, reuse, early release) is the lever, before the repetition factor R even enters.
- For `dfthcsos` a local circuit win can lose: a factorisation that shrinks the ANGLE lookups but raises Λ (or
  raises E_gap, which sits far below Λ here) raises `λ_eff`, so the cost goes up and the score goes down. Angle lookups are about 88 % of the reference T and the
  inner-prep temporaries about 75 % of its Q (`tasks/dfthcsos/README.md`), so the ANGLE circuits are the main
  lever, but the classical fit, the tree and the QROM layout are one joint objective.

## 3. Hard constraints and rejections

- **One failing task rejects the whole zip.** There is no partial credit, and a single-task prize is paid to a
  selected submission that also contains two other valid circuits. A "focused single-task campaign" still needs
  three passing circuits.
- `invsqrt`: 64 shots per x over x = 1..3,133,452, i.e. 200,540,928 shots, and **zero failures** are allowed.
  Tolerance is 2⁻²⁴·β/√x turns. Exactly one register.
- `dqi`: 102,400 shots; failures are allowed and priced through ε⁺. The first failure costs about +0.45 %.
- `dfthcsos`: rejected if the Hamiltonian error is above 20 mHa, Λ ≤ 49.0 or E_gap ≤ 3.914898 Ha. Any ANGLE
  circuit wider than 128 qubits is rejected; 128 itself is allowed and our circuits use exactly 128.
  The `angle_k_*` files are numbered from 0 with no gaps and `submission.npz` must hold `U`, `W`, `H2_I`,
  `H1_I`, `Hsym_lower` and `tree_edges`.
- Zip layout: `invsqrt.kmb|kmx`, `dqi.kmb|kmx`, `dfthcsos/angle_k_<i>.kmb|kmx` plus `dfthcsos/submission.npz`.
- Official scoring takes roughly 45 minutes per submission; our house cap is 3 uploads per UTC day, checked by
  the ledger before the upload (`AGENTS.md`).

## 4. How verification works, and why grinding is pointless

The verifier fuzz-tests the circuit on computational-basis inputs. Because every kickmix instruction maps one
bit string to one bit string times a phase, a classical machine simulates the circuit one input at a time,
tracking one bit per qubit plus a phase; the simulator processes 64 to 512 inputs per CPU instruction and copes
with circuits of more than 100 million gates on one core. For each input it checks that the input is restored,
the scratch qubits are back at |0⟩ and the phase is right. Linearity does the rest: correct on every basis state
with clean ancillas means correct on every superposition.

Approximation is priced, not forbidden. If a circuit fails on a weighted fraction ε of inputs, its quantum
output is within trace distance 2√ε of the ideal; `dqi` turns that into the repetition factor R(ε⁺), while
`invsqrt` and `dfthcsos` demand their accuracy outright (zero failures; ≤ 20 mHa).

Random inputs and internal measurement outcomes are seeded from a salted cryptographic hash of the submission
(the Fiat–Shamir heuristic). There is no hidden test set, any byte change gets fresh draws, and the salt is
secret, so searching seeds or nonces for a lucky draw is wasted compute and is banned here (`AGENTS.md`). Local
runs use a fixed public salt (`PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`), which is why every local figure in this
repository is labelled "fixed salt" and why only the Kaggle score is the score.

A debugging rule of thumb: failures that move around between random inputs usually mean a missing
measurement-conditioned phase correction; failures pinned to the same boundary value usually mean arithmetic,
bit order or range reduction; a circuit that passes the output checks but leaves an ancilla set is simply
invalid.

## 5. kickmix in one screen

`kickmix` is the circuit representation and simulator in Google's open-source Qualtran project. A kickmix
circuit is built only from reversible classical gates (X, CNOT, Toffoli/CCX, controlled swaps), diagonal phase
gates (Z, CZ, CCZ, rotations) and measurement-based uncomputation (Hadamard–measure–reset, HMR, with
measurement-conditioned corrections). Two file formats exist: `.kmx` is text and convenient while debugging,
`.kmb` is binary and the only sensible choice at scale (the reference `dqi.kmb` is about 845 MiB and 86 million
operations). Registers are little-endian, index 0 is the least-significant bit; our generators assert this
(`tasks/invsqrt/affine.py`, `tasks/dqi/bm_forney/gu_linear.py`), and it is the first thing to check when a port
fails on x = 1.

Cost intuition on error-corrected hardware: Clifford gates (X, CNOT, Z, CZ, H) are cheap; Toffoli, CCZ, T and
arbitrary rotations consume distilled magic states and are what the metric counts. The classic trick is
measurement-based uncomputation: compute `a AND b` with one Toffoli, use it, then HMR the ancilla and cancel
the leftover sign with a cheap conditional CZ instead of paying a second Toffoli, roughly halving the expensive
gates of compute–copy–uncompute patterns.

## 6. Calendar and prizes (as published)

| Date (23:59 UTC) | Event |
| --- | --- |
| 2026-10-22 | Start |
| 2026-11-20 | Mid-Competition Milestone Prize: highest public-leaderboard score at this instant, **public notebook required**, kept public to the end |
| 2027-01-04 | Longest Leader Prize window closes; qualifying notebooks and datasets must be public by then |
| 2027-01-13 | Entry deadline and team-merger deadline |
| 2027-01-20 | Final submission deadline |

Prizes total $150,000: leaderboard $50k / $25k / $10k / $5k / $5k / $5k for places 1–6, plus $10k
Mid-Competition Milestone, $10k Longest Leader and three $10k single-task prizes (fusion, combinatorial
optimisation, chemistry). Every additional prize carries the same licensing, reproducibility and documentation
duties as the main prizes, which is why this repository regenerates every shipped circuit from its own committed
generator and records every parent with URL and licence (R10 in `AGENTS.md`). We compete solo; no team merger
(R11).

## 7. Per-task playbooks

### 7.1 invsqrt (fusion)

The reference follows the "fast inverse square root" recipe: range-reduce x, take a structured first guess,
refine with Newton steps `y ← y(3 − x y²)/2`, all in reversible fixed point. The search space is discrete and
small enough to sweep: interval count, polynomial degree and coefficient precision for the initial guess
(Chebyshev or Remez minimax, not Taylor, which is weak at interval ends), number of Newton steps, per-stage bit
widths (early Newton intermediates need fewer bits than the final phase register), truncated low partial
products, and the workspace schedule. Guard bits only where the error budget proves they are needed; the budget
has to cover approximation error, Newton truncation, fixed-point rounding, omitted partial products and
representation changes, with the worst case certified at the range boundaries. Compare a QROM first guess
against a polynomial one by compiled cost, never by classical operation count: the cheapest formula is not the
cheapest kickmix circuit.

Where we are: the shipped circuit is a 90-qubit Gray-curvature schedule with an exact-domain affine
Toffoli/CSWAP rewrite, 13.24× at Q 84, zero failures over the full shot count. The best public circuit we have
measured is 20.06× at 63 qubits, but its published replay depends on frozen circuits and certificates that are
not source, so it is not a generator we can ship under R10 (D-PRA320-01). Matching it from our own source is the
open invsqrt problem.

### 7.2 dqi (combinatorial optimisation)

A reversible finite-field decoder whose cost is dominated by Q². Attack peak qubit count first: draw the
register-liveness diagram and release registers as soon as they are dead. Compare GF(2¹²) multiplication and
inversion schedules by compiled cost. Only the final sign is needed, so avoid materialising the full decoded
objects. Imperfect decoders are allowed but must be judged only through R(ε⁺) under salted verification, keeping
a zero-failure reference path alongside any bounded-failure variant.

Where we are: a Berlekamp–Massey + Forney decoder ported from Apache-2.0 public notebooks, 54.73× at Q 889 with
zero value and zero phase errors at our salt. This equals the best public dqi we have measured, so the remaining
dqi upside is beyond the public frontier.

### 7.3 dfthcsos (chemistry)

The classical and quantum halves are one objective: `λ_eff × T × Q`. Search the factorisation rank (R, B, C),
pruning thresholds, Givens-tree topology and angle precision together, re-evaluating the 20 mHa, Λ and E_gap
constraints after every classical refit, and enforce the 128-qubit ANGLE width at generation time rather than at
packaging. On the circuit side, deduplicate angle data, exploit repeated prefixes and structured QROM windows,
and remember that T and Q are charged for the whole block encoding, so a saving inside one ANGLE circuit is
diluted by the parts of the encoding you do not control.

Where we are: 9.78× at T 16,366 and Q 430 (λ_eff from Λ ≈ 305.7, E_gap ≈ 3.9149 Ha, error_2 at 19.999 mHa,
i.e. right at the accuracy wall) with 15 five-word ANGLE circuits from a full-XOR J = 5 compiler on a public
(8, 143, 60) factor. The repository's negative-results register holds dozens of refit points that failed the
20 mHa rule; read `docs/decisions/` before repeating one.

## 8. The operating loop, mapped onto this repository

The guide's minimal loop (freeze baselines, reproduce the reference score, profile by subroutine, change one
thing, test, record, promote only reproducible deltas) is what the ledger enforces:

1. Reference identity and fixed-salt calibration: `harness/calibrate_reference.py`, `harness/reference_identity.py`.
2. One hypothesis per branch and per pull request, cut from `main` (`AGENTS.md`, merge queue).
3. Local score of a zip: `harness/score_local.py` (G0 preflight, full verification, task costs, geometric mean).
4. Gates G0–G5 on every candidate (`ledger/gates/`), ending in G5: the whole zip is rebuilt byte for byte from
   the committed generator and the declared, hash-pinned inputs.
5. Every run leaves a manifest with the candidate id, parent, commit, hashes, verifier results, costs and the
   keep/discard decision (`docs/ledger-schema.md`); failed hypotheses stay in `docs/decisions/` for good.
6. Upload only through `ledger.scorecard` (reserve → upload → record), 3 per UTC day, john-wick only.

Candidate gate before anything is called ready: official verifier passes at full shot count; ancillas clean;
cost recomputed from the exact serialised artefact; beats its parent under the official metric; deterministic
rebuild from a clean environment; licence and public-notebook duties understood. Archive gate: correct names and
folders, no numbering gaps, all `submission.npz` arrays present, every ANGLE circuit ≤ 128 qubits, the zip reopens
and re-verifies after packaging, and the submission log records UTC time and the remaining daily quota.

## 9. Where we stand (2026-11-02)

| | invsqrt | dqi | dfthcsos | geometric mean |
| --- | --- | --- | --- | --- |
| submission-011, local fixed salt | 13.2377× (Q 84) | 54.7295× (Q 889) | 9.7782× (Q 430) | **19.21** |
| best public circuit we measured | 20.06 (Q 63) | 54.73 | 8.91 | — |

Public score: **19.20572** (submission-011, anonymous leaderboard read 2026-11-02T17:47Z), rank 1,404 of 2,052
teams; the local fixed-salt figure matched it. Leader 27.99617 (Breaking1800); last paid place (6th) 26.80320. The
field is moving faster than we are: since the 2026-10-29 read our score rose from 18.39 to 19.21 while the rank fell
from 848 of 1,501 to 1,404 of 2,052 and the prize line rose from 24.74 to 26.80.
The ledger record of this read (`ledger/evidence/submission-011/kaggle-public-score.json` and the leaderboard block
of `ledger/standing.yaml`, which feeds the status page) lands with PR #81 (`op-vqcc/ledger-reconcile-1102`), not with
this guide; until that merges, `main` still records the 2026-10-29 read.

What the gap means: reaching the prize line from 19.21 needs the product of the three ratios to grow 2.72×
(26.80/19.21 cubed), i.e. about 1.40× on every task or the equivalent concentrated on one. Matching the best public
invsqrt we have measured (Kaggle publishes no per-task scores) alone would give (20.06 × 54.73 × 9.78)^(1/3) ≈ 22.1, well short of 26.80; the paid places need work
beyond the public frontier on at least two tasks, which is why own-generator invsqrt work and the chemistry factor search run in
parallel. The 2026-11-20 milestone prize additionally needs a public notebook, which we have not published
(`notebook_url: null` in `ledger/standing.yaml`).

## 10. What the source guide got wrong or left out

- **Prizes and dates.** It listed the $150k pool and the three single-task prizes but omitted the two
  notebook-gated prizes: the Mid-Competition Milestone (2026-11-20, $10k) and the Longest Leader (window to
  2027-01-04, $10k). Both require public notebooks and datasets, which changes what "ready" means for a
  November upload.
- **"A focused single-task campaign is strategically valid."** Only with three valid circuits: a failing task
  rejects the zip, and the single-task prize is awarded to a selected submission, not to a bare circuit.
- **Cost formulas.** It gave the dqi and chemistry factors symbolically. The definitions printed on the
  Kaggle evaluation page (read 2026-11-02; `tasks/dqi/README.md` labels the same R(ε) "inferred") are
  `R(ε) = ln 2 / (−ln(½ + 2√ε))` and `λ_eff = √(E_gap(2Λ − E_gap))`, and for chemistry T and Q are charged for
  the whole block encoding, not only the ANGLE circuits. It also did not say that invsqrt rotations are priced
  in T, which decides whether dropping a rotation beats adding a Toffoli.
- **Accuracy contracts.** It said invsqrt and dfthcsos "demand success" without the numbers: zero failures over
  200,540,928 invsqrt shots; 20 mHa, Λ > 49.0 and E_gap > 3.914898 Ha for chemistry; 102,400 dqi shots with
  about +0.45 % per first failure.
- **Campaign order.** It recommends profiling invsqrt first. Our measured standing says the biggest ratios came
  from dqi (Q²) and the hardest wall is chemistry's 20 mHa rule; invsqrt is where the public frontier is
  furthest ahead of us, so it is the right next target for a different reason than the guide gives.
- **Attribution.** Its sources check out: the companion paper is arXiv:2610.23832, the metric notebook is
  `kaggle.com/code/metric/google-quantum-ai-metric`, kickmix lives in `quantumlib/Qualtran/kickmix`, and the
  Google Open Source Blog announcement by Tanuj Khattar and Ryan Babbush is dated 2026-10-21 (the competition
  opened on 2026-10-22).

## 11. Glossary

- **Ancilla** — scratch qubit that must be back at |0⟩ when the circuit ends.
- **Block encoding** — a circuit that embeds a scaled Hamiltonian inside a larger unitary for phase estimation.
- **ε⁺** — upper confidence bound on the dqi decoder's failure rate; sets the repetition factor R.
- **HMR** — Hadamard, measure, reset: measurement-based release of a garbage qubit, leaving a sign to correct.
- **kickmix circuit** — reversible classical logic + phase gates + measurement-based uncomputation; monomial, so
  it is classically simulable one input at a time.
- **λ_eff** — effective normalisation of the chemistry block encoding, `√(E_gap(2Λ − E_gap))`.
- **QROM** — quantum read-only memory: a lookup table that answers every address in a superposition at once.
- **Toffoli** — controlled-controlled-NOT; the unit of expensive, non-Clifford cost in this metric.

## 12. Sources

- Kaggle competition pages (overview, evaluation, timeline, prizes), read 2026-11-02:
  <https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation/>
- Official metric notebook: <https://www.kaggle.com/code/metric/google-quantum-ai-metric>
- Companion paper: Khattar et al., *Leveraging verifiable structure in quantum circuits to find more efficient
  compilations with agentic AI*, arXiv:2610.23832.
- kickmix in Qualtran: <https://github.com/quantumlib/Qualtran/tree/main/kickmix>
- Google Open Source Blog, *Announcing the verifiable quantum circuit compilation competition on Kaggle*,
  T. Khattar and R. Babbush, 2026-10-21.
- Independent English field guide (CC BY 4.0), adapted from H. Tsukano, *Basic Knowledge for Google Quantum AI's
  Kaggle Competition: An Introduction to FTQC Circuit Optimization for Programmers*, v1.0, 2026-11-02.
- This repository: `tasks/invsqrt/README.md`, `tasks/dqi/README.md`, `tasks/dfthcsos/README.md`,
  `harness/costs.py`, `ledger/standing.yaml`, `docs/decisions/` (D-PRA320-01, D-PRA321-01, D-PRA341-02).
