# hermes-syed-v12: verified public portfolio and submission-012

## Result and immutable identities

- Kaggle submission **58301234**, submitted 2026-11-13 07:53 UTC, status **COMPLETE**, public score **27.00209**.
- Local full-shot geometric mean: **27.00208481418463**; latest G0–G5 records all PASS and `shipping_problems()` is empty.
- Generator commit used by the gates: `6890d0f19a10b94f3f7111743a4520d23c07c2e6`.
- Candidate ZIP: 49,305,565 bytes; SHA-256 `55ee2315fddb8622401fe616e6bcebacf9cffc87ce8c064dadc9d990dec2528c`.
- Parent candidate: `pra325-invsqrt-vendored-63q`.
- Circuits are the licensed Syed v12 **public portfolio**, not new independently synthesized circuit improvements. See `provenance.md`, `tasks/public_portfolio/SOURCE.json` and `notices/50-public-portfolio.txt`.

| Task | Q | Mean Toffoli | Local cost | Local ratio | Full shots |
| --- | ---: | ---: | ---: | ---: | ---: |
| invsqrt | 46 | 1511.570530021682 | 80162.75511623152 | 25.906971768922805 | 200540928 |
| dqi | 889 | 383156.28759765625 | 363800079945.19495 | 67.17828549099968 | 102400 |
| dfthcsos | 427 | 14810 | 296635967.5935997 | 11.312180432929868 | 78080 |

In invsqrt, the charged Toffoli-equivalent is **1742.668589483294**, including rotation synthesis; it is not merely the mean Toffoli count. The worst error/tolerance ratio is 0.973575996935943. DQI had two value errors and no phase errors; the verifier's confidence-adjusted repetition factor is **1.2013880602795501**. Even zero errors at the same 102400 shots would give R=1.19126, not 1. Chemistry has lambda_eff=46.907347493481, error_1=0.019610371288992016 and error_2=0.01999877989285481; both errors must remain strictly below 0.020. Individual ANGLE circuits are capped at 128 qubits; Q427 is the aggregate resource quantity.

## Reproduction and evidence

Run `run_candidate.py` from the repository root with the actual package root and the calibrated interpreter. Set `VQCC_DATA`, `VQCC_METRIC` and `VQCC_BASELINE` to the pinned local package, metric and reference JSONL. No binary package data is committed.

- `run_candidate.py` checks the exact ZIP identity, committed candidate paths and all 18 declared pins, and resumes the gate pipeline. It neither reserves a slot nor uploads.
- `G3.json` is the exact full-shot verifier evidence. The candidate/submission manifests preserve all gate records, including the initial G3 environment refusal rather than erasing it.
- `gates-first-attempt.txt`: G0–G2 PASS; G3 refused before simulation because the absolute kickmix path differed from the reference calibration. All 17 file hashes agreed.
- `gates-full-shot-pass.txt`: the retry with the calibrated main interpreter passes all gates. No salt or verifier acceptance rule was changed.
- `pytest.txt`: **709 passed, 16 skipped, 1 warning**. Earlier missing-`.pth` subprocess import failures were fixed through the existing `scripts/install_kickmix.py` setup before this run. The warning says the concurrent memo test did not exercise contention; optional fitting/notebook dependencies and unstaged factor inputs account for the skips.
- `pytest-publication-integrated.txt`: final integrated checkout **802 passed, 16 skipped**, with the same configured data, metric and baseline. An earlier publication attempt stopped at collection because VQCC_METRIC was not exported; the corrected run passed. This integrated count includes both branches and is not substituted for their individual branch results.
- `upload-attempts.txt` and `submission-record.txt`: real CLI outputs. Two rejected attempts were reconciled as failed after checking that Kaggle had no new row. The third uploaded a byte-identical copy named `submission.zip` and was recorded. The ledger contains the two failed reservations and the successful recorded reservation. There is one successful submission that UTC day, with no pending reservation.
- `upload_submission.py` is an archived copy of the **actual one-off uploader used**; the working-tree bytes were SHA-256 compared against the original script before publication. It contains machine-specific paths and is not a reusable supported CLI. It stages an identical file named `submission.zip`, verifies SHA-256, calls Kaggle, and reads the new submission reference. It must only be invoked inside the ledger-controlled submit workflow; do not run it to inspect results or test it against the real service. No credentials are in this script.

The 27.00209 score and COMPLETE status were independently read from Kaggle. The downloaded public leaderboard at 2026-11-13 12:41 UTC placed team 17188255 at rank 522 of 2972. Rank is time-dependent; the score is the durable result. At that read the leader scored 29.90871 and sixth place scored 28.56411.

## Research follow-up

Three different-model workers tested the attached roadmap against the stronger v12 baseline; none produced a better verified circuit. The detailed findings and limits of those tests are in `docs/handoffs/hermes-five-review-findings.md`. The separate search-fitness validation fix prevents incomplete/nonfinite feasible records from receiving favorable scores; it does not account for this submission's score increase.

Starting from 27.00209, reaching 30.0 requires the product of the three task costs to fall to approximately 0.72917 of its current value: about a **27.08% cut in one task**, or **9.99% in each task**. These are mathematical targets, not achieved scores. The next research brief is `docs/research/notebook-next-frontier-prompt.md`.
