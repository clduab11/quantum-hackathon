# PRA-250: submission-9 DQI source port

SomeJoint v7 kernel 140675727 is the source. Its cell 13 identifies this DQI as
unchanged from submission 9. The pre-port provenance read, including all 58
embedded file hashes, is preserved in `tasks/dqi/hankel/PROVENANCE.md`.

`tasks/dqi/generate_hankel.py --out DIR` adds a fixed variant alongside #33.
It uses the Hankel/Bezoutian phase path and cyclic Gold-26 cubes; the existing
paired arithmetic and Praxen trace/Lagrange projection are reused. No DQI
circuit, external table, notebook output or package circuit is an input.
The inherited decoder's rare degree-gap approximations remain; neither small
exact tests nor finite verification shots establish universal correctness.

Engineering lenses: **Read before you write** (reuse audited arithmetic),
**Smallest diff that solves it** (fallback unchanged), **Test the failure first**
(three tests failed before modules existed), **Say what you did not check**.

## Build and first-build correction

The first build used the inherited small-space inverse directly, overlooking
an upstream runtime substitution to norm recycling. Static T was 998017:
1188 extra gates in phase correction. Full fixed-salt verification nevertheless
passed 102400 shots with 0 value errors, 0 phase errors, mean T
997236.2740332031, R=1.1912604648115832 and cost 926245696824.9564.
SHA-256: `81a03e7fd3cc1d2ca63d0858366706aff9885e8758a20457264a52ce70f31765`.
This measurement is retained and is not the candidate.

The source-fidelity fix explicitly imports `init_norm_recycle_inverse` in
border scaling. The final static counts match the public source exactly:
Q=883, T=996829; stage T = 309812 / 78996 / 219213 / 78996 / 309812.
The 809910127-byte circuit has SHA-256
`17df18286ae5713fd08584cb616116f800c2eed92dce1566f78310f187c58c52`.
It differs from the public hash because our independently written projection
emits a different Clifford sequence. That hash difference is not hidden.
No seed, salt, threshold, or variant was selected by verifier results.

## Candidate contract

`configs/gates/pra250-hankel.yaml` binds this DQI, current invsqrt and the
already merged chemistry generator at Gluzdov v8 / J=10 / 11 bits. PRA-247
independently verified that chemistry family. Our candidate must verify its
own exact zip; those other results are not substituted for its G3.
The sole non-circuit input is the pinned Gluzdov NPZ, copied under D-PRA211-05.
Full shots are invsqrt 200540928, DQI 102400 and chemistry 36608.
Salt 0001 is fixed. Salts 0002/0003, if run, are diagnostics only.

## Verification boundary

Five focused tests pass, including all 4096 cube inputs with a nonzero target,
phase equality against an independently evaluated Forney formula, polynomial
restoration, fallback-hook restoration on exceptions and source pins.
Full-suite, candidate-gate and diagnostic outputs will be appended below.
No Kaggle upload, merge, live-system action or Adjudicator verdict is claimed.

## Full fixed-salt result

102400 shots: PASS, zero value errors and one phase error. Mean T=996048.1979785156; epsilon+=0.0009104197583220583; R=1.1967314991687559; cost=929391044803.9614. Ratio versus the requested rounded reference 2.4439e13 is 26.295712807×. The ledger uses the calibrated reference 24439465632206.816. The 25× floor passes; the 26.42× target is not reached on this salt.

The public notebook reports one observed phase error in 307200 shots and two inferred from Kaggle in 102400. It does not supply a matching fixed-salt baseline. The phase-noninferiority acceptance condition remains unresolved; question 65ae1ed2-b894-47e0-8d76-2a9d435b83d1 requests that evidence. It is not safe to compare unlike samples or to switch to the earlier inverse because it happened to have zero errors.

Commands and actual output:
```text
uv sync
Resolved 96 packages; Checked 36 packages
uv run pytest -q tests/test_dqi_hankel.py  # before implementation
3 failed
uv run pytest -q tests/test_dqi_hankel.py  # final focused checks
5 passed in 0.76s
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run pytest -q
356 passed, 7 skipped in 256.57s (0:04:16)
uv run python -m ledger.registers check
OK registers: 245 decisions, 6 notice files, legacy index unchanged
```
The seven skips need optional GPU/notebook dependencies. No test was disabled. The first notice check rejected an added blank line; the line was removed and the register check passes. Evidence files contain the actual output.

Governed GitHub discovery returned `gateway_token_revoked`; publication and remote-tree comparison are pending. No alternative credential route was used.

The official verifier derives its input and measurement seeds from the circuit SHA-256 plus salt (`verify_submission_dqi.py`, `_initial_seed`). Different circuit bytes therefore change the sampled inputs even with the same salt. This explains why structural-equivalence claims cannot substitute for the missing public-build measurement. No explicit seed override was used.

## Three-salt diagnostic (measurement only)

| Salt | Shots | Value errors | Phase errors | Mean T | R | Cost | Ratio vs 2.4439e13 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0001 | 102400 | 0 | 1 | 996048.19797852 | 1.1967314992 | 929391044803.9614 | 26.295712807 |
| 0002 | 102400 | 0 | 0 | 996048.13126953 | 1.1912604648 | 925142134759.7561 | 26.416481405 |
| 0003 | 102400 | 0 | 1 | 996048.18498047 | 1.1967314992 | 929391032675.7648 | 26.295713151 |

All three used the same final circuit bytes, full 102400 shots, and fixed labels PRA171_LOCAL_PUBLIC_FIXED_SALT_0001/0002/0003. No explicit seed override. Salt 0001 remains the candidate result. Aggregate two phase errors in 307200 shots is not a same-sample comparison with the public notebook's one observed error in 307200. No candidate change follows from this diagnostic.

## Exact-zip G0–G5

All real gates passed on the exact bundle; no waivers. G4 first failed because the
parent was named by submission id. The parent was corrected to the measured
candidate `pra233-2-dqi-q881`, whose zip hash equals submission-004. The failed
receipt is retained, followed by the passing rerun. No circuit bytes changed.

Commands:
```text
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=. uv run python ledger/evidence/pra250-hankel/run_candidate.py
G0 PASS; G1 PASS; G2 PASS; G3 PASS
G4 FAIL: parent submission-004 has no measured geometric mean in the ledger
# Correct parent link; rerun reuses completed gates, with no waivers.
G4 PASS; G5 PASS
shipping_problems: []
```

G5 rebuilt from local generator commit `4305da8c289684e122c4a7fc8e604e5c5ab86ae7`. Every task has empty missing/extra/changed lists. Only the declared non-circuit chemistry factor was copied. This commit is not yet published; no remote-tree equality is claimed.

| Task | Shots | Cost | Calibrated ratio |
|---|---:|---:|---:|
| dfthcsos | 36608 | 808679648.9839141 | 4.149479453986215 |
| dqi | 102400 | 929391044803.9614 | 26.29621381531806 |
| invsqrt | 200540928 | 157751.94999626835 | 13.16480863637127 |

Local geometric mean: 11.283239253337468. G3 uses the exact same DQI circuit and confirms zero value errors and one phase error. The local numerical gates pass, but the task's matching-public phase comparison is still open.

Durable zip: `/home/cld-main/work/vqcc-data/queue/pra250-hankel.zip`.

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
| dqi.kmb | 809910127 | `17df18286ae5713fd08584cb616116f800c2eed92dce1566f78310f187c58c52` |
| invsqrt.kmb | 234743 | `75e8a0e2341bb3e8f8ded1ec1d53e24437410c69e887da9daf7d49bfcc28c2dd` |
| pra250-hankel.zip | 43263149 | `459b2f11778f5bbd576ce69b9f85156ca2c301bd2a3f74752adca5c2dadcbec7` |

## Remaining work and rollback

GitHub publication, pull_request registration, remote/local tree comparison and whole-queue merge-gate PASS remain incomplete. Tool discovery returned `gateway_token_revoked`; connection discovery returned `HTTP 403: Runtime tool token is no longer active`. The ordinary merge-gate command failed its anonymous open-PR enumeration with HTTP403 rate limiting. John Wick owns arranging restoration of the governed session and supplying the public phase baseline through saved question 65ae1ed2-b894-47e0-8d76-2a9d435b83d1. Sofia then publishes one PR and reruns the whole queue gate. No alternative access or credentials were used.

This bundle is not an acceptance or upload recommendation while the phase condition is unresolved. John Wick alone uploads; the board merges; the separate sign-off/re-check process remains intact. The unchanged #33 generator and its frozen config remain the fallback. No production setting, live stack or main branch was changed.
