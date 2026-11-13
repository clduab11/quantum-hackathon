# hermes-mix-20261113: verified three-source public mix and submission-013

## Result and immutable identities

- Kaggle submission **58321543**, submitted 2026-11-13 21:26:56 UTC, status **COMPLETE**, public score **27.28993**.
- Local full-shot geometric mean: **27.289927495685724**; G0–G5 records all PASS and `shipping_problems()` is empty.
- Generator commit used by the gates: `84ace33df544d5084ff3b8cec111fc3e74268348`.
- Candidate ZIP: 49,289,018 bytes; SHA-256 `d82625a236b378293a755487e3c83d66401042ba6473bca9e0710c6b0d425665`.
- Parent candidate: `hermes-syed-v12`.
- The circuits are copied unchanged from three public Kaggle notebook outputs: ahoirg V25 (invsqrt), areebbb V8 (dqi) and atakanaldemir V19 (dfthcsos factor and its 15 angle circuits). They are **not** our own synthesis. See `provenance.md`, `tasks/public_portfolio/MIX-20261113.json`, `notices/51-public-mix.txt` and D-HERMES-20261113-01. Each notebook page says Apache 2.0. The full licence and lineage review is deferred, and must be done before 2027-01-20.

| Task | Q | Mean Toffoli | Local cost | Local ratio | Full shots |
| --- | ---: | ---: | ---: | ---: | ---: |
| invsqrt | 46 | 1480.7509794908299 | 78765.64938067834 | 26.366496690430722 | 200540928 |
| dqi | 889 | 382600.1887988281 | 360209722458.61554 | 67.84787891174888 | 102400 |
| dfthcsos | 427 | 14750 | 295360007.9919914 | 11.361049219657804 | 78080 |

For invsqrt, the charged Toffoli-equivalent, which includes rotation synthesis, is **1712.2967256669206**. The worst error-to-tolerance ratio is 0.9494158703926416.

DQI had no value errors and no phase errors. The verifier's confidence-adjusted repetition factor is **1.1912604648115832**.

Chemistry has lambda_eff = 46.89556749763687, error_1 = 0.019999997999999998 and error_2 = 0.01999999799999986. Both must stay strictly below 0.020, so the margin is about 2e-9, much thinner than v12's. Any change to this factor table or to the verifier settings needs a fresh full-shot G3.

Each ANGLE circuit is capped at 128 qubits. Q427 is the aggregate resource quantity.

Relative to `hermes-syed-v12`, the cost ratios are 1.01774 for invsqrt, 1.00997 for dqi and 1.00432 for dfthcsos. These are measured by G3 at the same fixed salt.

## Reproduction and evidence

Run `run_candidate.py` from the repository root with the pinned package root and the calibrated interpreter. Set `VQCC_DATA`, `VQCC_METRIC` and `VQCC_BASELINE` to the pinned local package, metric and reference JSONL. No binary package data is committed.

- `run_candidate.py` refuses to run unless the ZIP identity matches and the candidate paths are committed. It checks all 18 pins against `MIX-20261113.json` and resumes the gate pipeline. It neither reserves a slot nor uploads.
- `G3.json` is the full-shot verifier evidence.
- `gates-full-shot-pass.txt` is the gate run on commit `84ace33`. All six gates passed, and G5 rebuilt every task byte for byte from the three pinned notebook outputs.
- An earlier start stopped before any gate ran and wrote no manifest. An untracked local notes file had made the worktree count as uncommitted. That file is now in `.git/info/exclude`, and nothing else changed.
- `pytest.txt`: **751 passed, 16 skipped, 1 warning** at `84ace33`. The warning is the concurrent memo test not exercising contention.
- `upload-attempts.txt` and `submission-record.txt` are the real CLI outputs. There was one upload attempt, through `ledger.scorecard submit` on reservation slot 2 (`2026-11-13-slot2-56007098`), and it was recorded.
- `upload_submission.py` is a byte-identical copy of the one-off `hermes-syed-v12` uploader, which was the script actually used. It stages a file named `submission.zip`, verifies its SHA-256 and calls Kaggle. It must only run inside the ledger-controlled submit workflow. It contains no credentials.
- `kaggle-result.csv` is our row from the Kaggle submissions list. `ledger/evidence/submission-013/kaggle-public-score.json` records the score and the leaderboard read.

The 27.28993 score and COMPLETE status were read from Kaggle. The public leaderboard downloaded at 2026-11-13 21:54:55 UTC placed team 17188255 at **rank 140 of 3002**: 104 teams score higher, and 36 (us included) share 27.28993. At that read the leader scored 29.90871 and sixth place scored 28.56411, which is 1.27418 above us. Rank changes over time; the score is the durable result.
