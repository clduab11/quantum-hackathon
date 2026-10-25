# PRA-238: invsqrt resource study

**Verdict: NO-GO for the bounded port onto our 90-qubit schedule.** The tested
16-bit carry accumulator preserves the integer result on all 3,133,452 inputs.
Even allowing an unproved parity refit, three-position Cuccaro prefixes, and the
entire published normalisation/fused-phase saving gives **14.254×**, below 15.0×.
This is a design-study rejection, not a lower bound on all possible invsqrt
circuits. No new quantum candidate, zip, full-shot run, or upload was made.

The 15-bit alternative has a measured negative result: a signed two-bit counter
cannot represent the final carry on **38,871 inputs**, first **x = 5**. Its final
range is −2..2. The 16-bit alternative has range −1..1 and zero overflows.
The unbounded integer calculation itself agrees in both experiments; it is the
proposed two-bit physical representation that fails at width 15.

## Scope and evidence

Base: `5bb5792`, branch `op-vqcc/PRA-238-invsqrt-study`, separate worktree per
D-PRA232-02. The harness PRA-233 planning branch is untouched. The latest PRA-238
retarget supersedes the old 14.5× gate. Exact 15× cost is 2,076,774 / 15 =
**138,451.6**; 138,452 in the assignment is rounded. Target 16× costs 129,798.375;
stretch 17× costs 122,163.176.

Labels: **measured** means reproduced here; **model** means counted with explicit
assumptions; **stated** means a source's result, not a verifier result we obtained.
Small JSON evidence lives in [pra238/](pra238/). The production generator and
coefficient recipe are unchanged. The baseline exhaustive mirror reproduced
SHA-256 `75e8a0e2341bb3e8f8ded1ec1d53e24437410c69e887da9daf7d49bfcc28c2dd`,
90 qubits, 1,448 static / 1,437.5 expected Toffolis, 44 rotations, and model ratio
13.164808753447378. It checked 3,133,452 inputs and 4,194,304 derivative-split
pairs, with phase match true and positive calibrated margin 73,326,605 units.
This does not repeat the old 200,540,928-shot verifier run.

## Where the resources go

`uv run python -m tasks.invsqrt.study_profile` constructs and counts the existing
raw schedule without simulating it. Scalar gate totals are checked against
Kickmix operation statistics; live allocation maximum is checked against its
qubit count. All numbers below precede affine compilation and calibration.

| Stage | Static Toffolis | Peak live qubits |
|---|---:|---:|
| Normalisation | 98 | 46 |
| 256-entry ANF coefficient lookup | 247 | 87 |
| Inner Horner forward | 85 | **90** |
| High-word phase | 66 | 89 |
| Outer Horner forward | 280 | **90** |
| Low-word phase | 162 | 81 |
| Outer Horner inverse | 280 | **90** |
| Curvature reload | 17 | 63 |
| Inner Horner inverse | 85 | 62 |
| Deferred lookup phase repair | 22 | 41 |
| Inverse normalisation | 100 | 41 |
| Derivative coarse join and inverse | 12 | 82 |
| **Total** | **1,454** | **90** |

Affine rewriting/peephole reduce 1,454 to 1,448 static Toffolis; conditional
execution discounts another 10.5 to 1,437.5 expected. Do not distribute those
savings among stages without profiling the compiled circuit. The profile counts
48 phase emissions, including Clifford operations; the compiler/calibration
report is authoritative for the final 44 non-Clifford rotations.

The persistent allocation after lookup is 22 input + 5 flags + 7 curvature +
12 derivative residual + 7 derivative coarse + 21 low anchor + 8 high anchor =
82. Inner forward needs eight extra carry qubits after borrowing two proven-zero
wires, reaching 90. The curvature checkpoint releases two bits before high
phasing. High phasing adds nine extension qubits, reaching 89. After releasing
the high word, outer rows have 72 persistent qubits and 18 extra carries, again
90. Layout `(w1, LB, S, whi) = (18, 21, 20, 8)` is confirmed by the mirror.
The input register remains 22 bits; it cannot be counted as disposable workspace.

The existing schedule already has HMR lookup erasure, deferred repair, curvature
checkpoint/reload, a shared normalisation prefix, zero-target shift moves,
normalized-top carry borrowing, and an exact-domain HMR/conditioned-CZ rewrite.
**Read before you write:** none earns a second saving merely by being renamed.

## Carry-save integer experiment and cost model

The three widest outer rows (13, 12, 11) run normally. Split the low accumulator
at bit `m`; run the remaining eleven signed rows into its bottom `m` bits and
accumulate the quotient in a separate signed counter. Fold the counter into the
upper word once. `carry_step` uses exact Euclidean division, including negative
terms. The experiment regenerates our table from the specification, checks every
input and every prefix, and compares the reconstructed result against the
existing integer pipeline. No imported coefficient file is an input.

At m=16 the largest term is 32,672, so each row needs only a single carry/borrow
update. A favorable gate model uses 16 Toffolis for a carry-out addition plus one
for the two-bit counter, three ordinary 20-Toffoli rows, and four to fold into the
five upper bits: `11*17 + 3*20 + 4 = 251`, versus 280 per direction. Saving:
**58 Toffolis total**. This assumes reversible sign handling and cleanup at no
extra cost; it is optimistic, not a compiled gate count.

The counter adds two qubits. On its own, the unmodified wide rows reach Q92.
For a combined estimate, grant removal of one residual bit and its carry bit
through a successful parity refit (up to 16 inner-row Toffolis saved). Grant three
Cuccaro prefix positions on all three wide rows, in both directions (+18
Toffolis, −3 carry wires). Then the inner and outer peaks both reach Q88:
outer `72 - 1 + 2 + 18 - 3 = 88`; inner `90 - 2 = 88`.
This is more generous than blindly porting a one-bit prefix. A parity refit and
quantum uncomputation have **not** been implemented or certified.

Using the published cost differences for EXP-222a and EXP-225a grants a further
`(141462 - 138095)/82 = 41.061` Toffoli-equivalent saving. This deliberately grants
the whole saving, although overlap, circuit layout, and rotation-margin transfer
are unproved. The final estimate still misses the bar. It is a scenario, not a
mathematical upper bound on every redesign.

## Lever table

All local arithmetic estimates use `cost = Q*(Toffoli + synthesized_T/4)` and
reference 2,076,774. Unless stated, rotations = 44 and synthesized T = 1,261
(rounded from the baseline report). Thus the tabulated baseline cost 157,747.5
is slightly below the full verifier's approximately 157,752; this rounding does
not change any verdict. Fractional Toffolis in phase-credit rows include an
assumed equivalent-cost credit, not a physical gate count. Rows are alternatives,
not additive savings.

| Lever/scenario | Q | Expected Toffoli or equivalent | Rotations | Cost | Ratio | Confidence / packet link |
|---|---:|---:|---:|---:|---:|---|
| Baseline | 90 | 1,437.5 | 44 | 157,747.5 | 13.165× | High; mirror and profile |
| Half-size lookup, ideal 127-Toffoli saving, no extra polynomial cost | 90 | 1,310.5 | 44 | 146,317.5 | 14.194× | Low; optimistic screen, packet §6 |
| Drop one inner row, grant 22-Toffoli saving | 90 | 1,415.5 | 44 | 155,767.5 | 13.333× | Low; tolerance unproved |
| Drop one outer row, grant 40-Toffoli saving | 90 | 1,397.5 | 44 | 154,147.5 | 13.473× | Low; tolerance unproved |
| Rotation-margin allowance, 11-equivalent saving | 90 | 1,426.5 | 44 | 156,757.5 | 13.248× | Low; older Alex study, not a measured local gain |
| More HMR lookup cleanup / existing affine HMR rewrite | 90 | 1,437.5 | 44 | 157,747.5 | 13.165× | High for present implementation; A.5 overlaps existing method |
| Parity refit alone, optimistic width/carry reduction | 89 | 1,421.5 | 44 | 154,570.8 | 13.436× | Low; high-phase peak remains; A.2/A.5 |
| Normalisation ladder + fused phase, grant whole public cost credit | 90 | 1,396.439 | 44 | 154,052.0 | 13.481× | Low transfer confidence; inner/outer peaks remain; A.2 |
| 16-bit carry-save alone | 92 | 1,379.5 | 44 | 155,917.0 | 13.320× | Integer range high; quantum resource estimate low; A.5 |
| Carry-save + parity + three-position Cuccaro prefixes | 88 | 1,381.5 | 44 | 149,314.0 | 13.909× | Low; assumptions above |
| Same + whole public normalisation/fused-phase credit | 88 | 1,340.439 | 44 | **145,700.6** | **14.254×** | Optimistic combined scenario; **NO-GO** |
| Public arithmetic-equivalent budget transplanted at Q88 (T=1,276.4) | 88 | 1,365 | 44 | 148,200.8 | 14.013× | Sensitivity only, not a port |
| Public EXP-225a comparison (T=1,276.4) | 82 | 1,365 | 44 | 138,096.2 | 15.039× | Stated, rounded; A.2; cannot be a parent |

**Structured lookup:** current ANF costs 247, already below a 255-node naive
unary tree. SELECT-SWAP needs additional output banks (55 bits per full table
word), so its smaller select cost cannot be treated as a free Q reduction.
No concrete banked schedule with a passing model was found. The half-table row
is deliberately favorable: a cubic needs another multiplication and accumulator;
we did not assume those costs vanish in a build decision. The older Alex study
reports that its smaller cubic lookup lost to extra arithmetic, consistent with
this screening result but not proof for our schedule.

**Rotation alternatives:** the synthesized T allowance is tied to the absolute
calibrated slack and shared across all rotations. A coarser angle or dropped
rotation needs a new exhaustive phase certificate. Arithmetic phase kickback
requires preparing a gradient register and extra reversible additions; counting
only the removed Z rotations misses those costs. No numeric passing model for
that alternative is established.

**Q-only changes:** removing already-erased lookup workspace cannot lower the
forward-inner peak. Further curvature erasure needs recomputation and must also
move that earlier peak. A full Cuccaro replacement raises arithmetic cost, while
the high-phase peak remains unless separately changed. The prefix scenario
above accounts for the cheaper mixed approach. A general grouped-curvature /
virtual-low-bit schedule like the public 84-qubit parent is a larger redesign,
not an established saving on our current schedule.

At Q88 and synthesized T=1,261, 15× requires Toffoli ≤ **1,258.064**, another
82.375 equivalents below the optimistic combined scenario. Holding that scenario's
arithmetic fixed requires Q≤83 (integer Q); 16× requires still more. The research
packet reports a public result, not evidence that these changes compose to Q82 on
our different starting schedule.

## Sources, provenance, and limitations

- [PRA-234 research packet](/PRA/issues/PRA-234#document-research-packet), revision
  `1c79889f-a3ac-40b6-8b5b-e5b90a46e466`, A.2 and A.5: comparison and parent restriction.
- [phucthaiv02 portfolio](https://www.kaggle.com/code/phucthaiv02/qcc-verified-portfolio-df-thc-retraining-study),
  public kernel pull 2026-10-25, API version metadata 11, source SHA-256
  `6d0e9fd742582f73ae891f03d5991b6948f695b7d5d9a0ee9e3af878d705d5e9`.
  Prose method reference only: carry-save grouping, parity refit, Cuccaro prefix,
  normalisation ladder, fused phase. Packet labels its licence Apache-2.0; we did
  not use its binary, table, or execute notebook cells. Version labels inside
  its prose exceed API metadata, so the exact source hash identifies this read.
- [Alex Chilton cost anatomy](https://www.kaggle.com/code/alexchilton/where-the-toffolis-go-anatomy-a-cheaper-invsqrt),
  latest public pull metadata 17 (packet cited 16), source SHA-256
  `605a37c3e6dfdde8a2e7078505ddad7df3f89447481443742440ee5ba821f94d`.
  Used only for qualitative tradeoffs; no code copied or executed.
- Local methods: `schedule90.py`, `signed_digit.py`, `affine.py`, `calibrate.py`,
  `fit_coefficients.py`, `mirror.py`. Existing coefficient provenance remains
  `regenerated; dataset-adapted calibration; licence unresolved` (D-PRA220-01).
  This study does not broaden its inputs or change the upload ruling.

No `fusion/*.npz`, selected circuit, `code/coefficients.json`, or
`invsqrt_calibration.json` was loaded. No public binary was used as a parent.
Only the existing recipe generated coefficient integers. Public resource claims
were not independently full-shot verified. Gate arithmetic for new quantum
cleanup and the proposed parity refit is not certified. There is no G0–G5 or
`shipping_problems()` claim for a nonexistent candidate.

## Reproduce

```sh
uv sync
uv run python scripts/install_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation
uv run python -m tasks.invsqrt.mirror
uv run python -m tasks.invsqrt.study_profile
uv run python -m tasks.invsqrt.design_study
uv run pytest
uv run python -m ledger.registers check
uv run python scripts/merge_gate.py --ref mine=HEAD
```

The baseline mirror ran before any simulator-based tests. The new numerical
experiment invokes no quantum simulator. **Test the failure first:** tests first
failed on the absent module; removing the carry quotient then produced three
failures (negative carry, positive overflow, negative accumulated carry).
Restoring it produced `6 passed in 0.03s`. Final suite and merge-gate output are
recorded on PRA-238 and in the PR. A negative study changes no deployed behavior;
any subsequent candidate must meet the original exhaustive-mirror, exact-zip,
full-shot, provenance, and review gates.
