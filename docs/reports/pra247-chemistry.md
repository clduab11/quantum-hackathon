# PRA-247 chemistry candidate: input and resource measurements

The declared Gluzdov v8 factor passes the unmodified numerical verifier. No
candidate batch size has been selected yet: the ticket asks for the smallest J,
while T1 recommends the largest fitting J. John Wick has the resource table below
in question card `79f6c7eb-7ac8-4c95-8e0b-0abbac323d43`.

These are numerical-factor and static circuit-resource results, **not** a full
circuit verification or an exact-zip G0–G5 pass. No shipping claim is made.

## Input

- Dataset: `dmitriigluzdov/vqcc-femoco-public-factorization`, version 8.
- Parent: <https://www.kaggle.com/datasets/dmitriigluzdov/vqcc-femoco-public-factorization?datasetVersionNumber=8>.
- Licence and author provenance: T1, PRA-245 / PR #40; Apache-2.0 as reported there.
- File: `inputs/thc/femoco_thc_r5.npz`, 1,871,575 bytes.
- SHA-256, independently checked:
  `809a992900937425f01a0593803921873f7bb472d590592c378d3ceb23657df5`.
- Shape: R=1, B=496, C=384, N=76; 572 addresses, 75 angles, 11-bit words.
- The shipping wrapper checks the input hash before creating outputs, copies
  the non-circuit input byte-for-byte, and calls our committed ANGLE builder.
  It has no Google reference-factor fallback and performs no refitting.

## Numerical verification, 2026-10-26

Calls: `load_inputs`, `load_tree_edges`, `evaluate_words(..., brot=11)`, and
`tasks.dfthcsos.checks.acceptance_problems`. Input words are unchanged.

| Metric | Measured value |
|---|---:|
| error₁ (Ha) | 0.006383440998581123 |
| error₂ (Ha) | 0.019999496917408252 |
| Λ | 294.45331358012606 |
| E_SOS (Ha) | -22144.18824805 |
| E_gap (Ha) | 3.914898049999465 |
| λ_eff | 47.855856272347104 |

`acceptance_problems` returned `[]`. The E_gap margin is approximately
5.0e-8 Ha; full verification must independently recover the circuit words.

## Static resource model

For each J=1 through 11, build every XOR-difference circuit using
`batch_deltas` and `build_qrom(brot=11, bank_bits=0, scratch=8, pebble_degree=4)`.
Sum twice the static Toffoli count and call the verifier's `resource_costs`.
The method is PRA-232's lower-cost direct traversal. This is structural resource
enumeration, not salt or seed selection. The reference chemistry cost is
3,355,599,588.3155365. Ratios are that cost divided by λ_eff × T × Q.

| J | ANGLE width | Total T | Score Q | Predicted ratio |
|---:|---:|---:|---:|---:|
| 1 | 29 | 95426 | 734 | 1.001088014 |
| 2 | 40 | 53946 | 745 | 1.744695015 |
| 3 | 51 | 39360 | 756 | 2.356449602 |
| 4 | 62 | 32628 | 767 | 2.801878015 |
| 5 | 73 | 28140 | 778 | 3.202811292 |
| 6 | 84 | 25896 | 789 | 3.431826721 |
| 7 | 95 | 23652 | 800 | 3.705759100 |
| 8 | 106 | 22530 | 811 | 3.837540706 |
| 9 | 117 | 21408 | 822 | 3.984621991 |
| 10 | 128 | 20286 | 833 | 4.149479454 |
| 11 | >128 | — | — | rejected by builder |

J=8 is the smallest value meeting the 3.8× floor in this traversal. J=10
has the lowest predicted cost and reaches exactly the ANGLE cap. The cap is
on each ANGLE circuit; score Q also includes state preparation workspace.

| Heuristic stage | T | Persistent Q | Temporary Q |
|---|---:|---:|---:|
| Outer preparation | 327 | 40 | 90 |
| Inner preparation | 7833 | 43 | 640 |
| Givens | 3150 | shared | shared |
| Heuristic total | 11310 | 83 | 640 |

Full shots for this factor are 572 × 64 = 36,608. The old factor's expected
254,464 shots must change in the candidate config, without reducing shots per
address. Companion tasks retain their full-shot requirements.

## Remaining verification

Resolve J, wire the selected generator and input pin into the gate config,
then build and fully verify the exact bundle. G5 must stage only the declared
input and regenerate all circuits. The companion DQI must match submission-004
and invsqrt must stay current. The final manifest, receipts, per-stage real
metrics, runtime and merge-gate report remain to be recorded.
