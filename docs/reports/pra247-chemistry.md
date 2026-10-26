# PRA-247 chemistry candidate: input and resource measurements

The declared Gluzdov v8 factor passes the unmodified numerical verifier. John Wick
selected **J=10** in question card `79f6c7eb-7ac8-4c95-8e0b-0abbac323d43`:
use the best verified ratio within the inclusive 128-qubit ANGLE cap. This
supersedes the ticket's earlier "smallest J" wording; see D-PRA247-02 and
D-PRA202-17 (PR #44). J=9 is a fallback only if J=10 fails full verification.

The exact bundle passed **G0–G5**, all real PASS, with full shots and the fixed public salt.
Chemistry measured **4.149479453986215×**, with a bundle geometric mean of
**10.876774669204233**. `shipping_problems()` is `[]`; the exact zip is in the
durable queue for John Wick. The PR is not merge-ready: the whole open queue
is blocked by PR #43, independently of these candidate checks.

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

## Candidate integration

The selected J=10 generator and input pin are in `configs/gates/default.yaml`.
The exact bundle is built from all eight freshly generated ANGLE circuits and
the recorded NPZ copy. The regenerated DQI and invsqrt hashes match
submission-004. `ledger/evidence/pra233-chem-v1/run_candidate.py` runs the real
checks with no waivers and logs the original harness reports, including elapsed
time. G4 enforces the 3.8× chemistry floor in addition to the existing strict
parent/archive improvement. G5 stages the declared input from the explicit root
`/home/cld-main/work/vqcc-data` and regenerates all three tasks.

The published generator commit is
`215309ccfa7cb452f48640b465ff1b2f00fee4f7` (tree
`eb1011ee639e766a737b5ae4851dbdb74bf7bdd4`, equal to local `67c1d22`).
PR #41 was merged before integration resumed; the remaining work uses branch
`op-vqcc/PRA-247-chem-candidate` cut from current main `9db5f61`.

```sh
OPENBLAS_NUM_THREADS=1 PYTHONPATH=. uv run python \
  ledger/evidence/pra233-chem-v1/run_candidate.py
```

The recipe refuses to overwrite an existing candidate. On interruption, inspect
the saved manifest and resume its uncleared gates with the same zip and config;
do not create a second candidate or repeat cleared checks.

## Full local verifier result

G3 used the unmodified competition verifiers. Fixed salt:
`PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`; shot_divisor=1; no waivers.
J=10 passed, so no J=9 fallback was needed.

| Task | Full shots | Cost | Ratio | Seconds |
|---|---:|---:|---:|---:|
| invsqrt | 200540928 | 157751.94999626835 | 13.16480863637127 | 71.445709 |
| dqi | 102400 | 1037527174785.328 | 23.55549447392886 | 85.959780 |
| dfthcsos | 36608 | 808679648.9839141 | 4.149479453986215 | 10.511709 |

The chemistry metrics exactly match the factor-only evaluation above. Each of
the eight circuits has 10 selection, 110 persistent word and 8 temporary qubits.
The scored width is 193 persistent plus max(90, 640, 8) temporary = 833.

| Stage | Toffolis | Persistent Q | Temporary Q |
|---|---:|---:|---:|
| ANGLE, both passes | 8976 | 110 | 8 |
| Outer preparation | 327 | 40 | 90 |
| Inner preparation | 7833 | 43 | 640 |
| Givens | 3150 | shared | shared |
| Total | 20286 | 193 | 640 |

G4 reports the parent/archive best at 6.76865313085382 versus this bundle's
10.876774669204233. The chemistry floor is enforced separately at 3.8×. The
parent is `pra233-2-dqi-q881`, the source candidate of submission-004.

These are fixed-public-salt local results, not a Kaggle score. Numerical
acceptance margins remain narrow; no salt selection or verifier changes were used.

## Tests and checks

```text
uv sync
Resolved 96 packages; Installed 36 packages
uv run pytest -q tests/test_chemistry_candidate.py  # before implementation
5 failed, 3 passed in 0.28s
uv run pytest -q tests/test_chemistry_candidate.py tests/test_ledger_gates.py
44 passed in 3.72s
OPENBLAS_NUM_THREADS=1 uv run pytest -q  # final source/test changes
356 passed, 7 skipped in 119.65s (0:01:59)
```

The skips require optional GPU or notebook dependencies. The initial full run
found one legacy Route A test tied to the changing default configuration; that
test now compares the historical contract against the frozen reference config.
No historical configuration was changed.

## File receipts

| File | Bytes | SHA-256 |
|---|---:|---|
| dfthcsos/angle_k_0.kmb | 439960 | `60d9dfb7a5ec6d172232f4d7081b858ce6868eea0ca2ee99ed3c99a195c3d0bb` |
| dfthcsos/angle_k_1.kmb | 443009 | `4079e0a08491fc3e42df613b09fd6c8399364bdf8cc508c0de2814f7ddf75c19` |
| dfthcsos/angle_k_2.kmb | 442839 | `cacdff488e6ea968f9f60f80072ca9285036b65a98a1cd60576190960458eb1a` |
| dfthcsos/angle_k_3.kmb | 447903 | `dbe4415e56782c83b6a53045ca7325a66528ae3812a28e577e0a527d89ba77bd` |
| dfthcsos/angle_k_4.kmb | 444852 | `6e0dcbe0f75a631c60e5d3affcf01179c4599abea05c053ef94d04e0a5f7d472` |
| dfthcsos/angle_k_5.kmb | 443878 | `58b75e436ff504af19b40fdb23337c7c548db8f84a3bdc9710d8f8303deee41f` |
| dfthcsos/angle_k_6.kmb | 448536 | `9df59056b173c4205a944c59edb4cfe5c77f0fd6003dbb34f2864910204b8d09` |
| dfthcsos/angle_k_7.kmb | 450307 | `86bc88ad3aad4553f60f3eac26807acd42a949ebc48bbb2443688193f9a9b1f4` |
| dfthcsos/submission.npz | 1871575 | `809a992900937425f01a0593803921873f7bb472d590592c378d3ceb23657df5` |
| dqi.kmb | 1040771980 | `dec77920d4b9f5964b6cd52c947aa0c91468d56b7ed28cd475fdfc18d067729d` |
| invsqrt.kmb | 234743 | `75e8a0e2341bb3e8f8ded1ec1d53e24437410c69e887da9daf7d49bfcc28c2dd` |
| pra233-chem-v1.zip | 105764340 | `66de2d131cc2c314e9683799866d8e76e6b2b434a8e9061c401037f1dbea28a8` |

## Rebuild and durable queue

G5 passed on published generator `215309ccfa7cb452f48640b465ff1b2f00fee4f7`.
All three tasks report `identical=true`, return code 0, and
`missing=[]`, `extra=[]`, `changed=[]`. The only staged input was
`inputs/thc/femoco_thc_r5.npz` at the declared SHA-256. Only that NPZ was
recorded as copied; every circuit was regenerated. G5 also rebuilt the zip
deterministically and checked its bytes against the exact gated archive.

Pipeline runtime: 449.881813981 seconds. All G0–G5 statuses are PASS; no waivers.
`shipping_problems()` returned `[]`. Durable zip:
`/home/cld-main/work/vqcc-data/queue/pra233-chem-v1.zip` (105,764,340 bytes).
SHA-256: `66de2d131cc2c314e9683799866d8e76e6b2b434a8e9061c401037f1dbea28a8`.
The same archive is recorded by `ledger/queue/pra233-chem-v1.json` and candidate
manifest `ledger/manifests/candidates/pra233-chem-v1.json`.

## Queue boundary and hand-off

The whole-open-queue gate currently fails at PR #43 (`331bb7dc3424`), even
when it is first after main. Conflicts: `notices/30-dfthcsos.txt`,
`pyproject.toml`, `uv.lock`. This branch does not touch those files. John Wick
was asked to route the repair to the author of PRA-251. The candidate's exact-zip
gates are complete; the PR must remain a draft until the whole queue passes.
The anonymous GitHub listing was rate-limited, so the complete open heads
#43/#44 were read through the governed GitHub connection and supplied via
`--pr` to the unchanged merge-order gate.

No upload, merge, live-system operation or Kaggle score is claimed. John Wick
submits under R-P2-2; The High Table routes the separate sign-off and re-check.
