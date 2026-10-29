# PRA-321 evidence: (8,143,60) chemistry through the full-XOR J=5 compiler

Candidate `pra309-chem-8-143-60` is submission-010 (`pra294-c59`) with only the `dfthcsos/` members changed. `tasks.dfthcsos.b143` regenerates 15 five-word ANGLE circuits from the declared SomeJoint factor and the committed plans. The factor is dataset `somejoint/qcc-our-chemistry-b143-c60-xor2` version 1 (`submission.npz`, SHA-256 `aef36d39b83bbbf696e909884218f6c02f067baef14a29de1c41306bc1f6395b`, licence field Apache 2.0, D-PRA211-05). The compiler is notebook `somejoint/quantum-circuits-22-67-local-gm-full-xor-chem` version 18 (source SHA-256 `b44fc04a99ab0c18afce4c7d8408ddc079dd8a87957e294d2102494d8d9b001a`, Apache-2.0). The dataset does not contain the compiler. The notebook does not contain the factor. No circuit or certificate is an input.

## Result

| | pra294-c59 (submission-010) | pra309-chem-8-143-60 |
|---|---:|---:|
| invsqrt.kmb | `17fc223d…41ad` | `17fc223d…41ad` (same bytes) |
| dqi.kmb | `7beea291…55f6` | `7beea291…55f6` (same bytes) |
| dfthcsos ratio | 8.589916214949021 | **9.778169511363153** |
| dqi ratio | 54.72947182918558 | 54.72947182918558 |
| invsqrt ratio | 13.237727705632725 | 13.237727705632725 |
| local GM | 18.39393056697713 | **19.205727125145224** |

19.205727125145224 is a **local GM**. It is not an uploaded score and it is not a public-leaderboard result. The parent local GM is 18.39393056697713. The last public score is 17.71949 (submission-009). Submission-010 is unscored.

Salt `PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`. Full shots. No salt or seed search.

- dfthcsos (G3, 78,080 shots): PASS, T 16,366, Q 430, cost 343,172,572.78, error_1 0.01582999310172256, error_2 0.01999880580061996, Lambda 305.662648282956, E_gap 3.914902197284391, lambda_eff 48.76425214813735.
- dqi (G3, 102,400 shots): PASS, 0 value errors, 0 phase errors, Q 889, T 474,307.7251367188.
- invsqrt (G3, 200,540,928 shots): PASS, Q 84, T 1,553.0002254402652, worst error/tolerance 0.9995943415273103.

Zip SHA-256 `a710cab21a8bac7ff552944ca48e8afb4e0fe4c98e0be5fd2e86be32b79c01ac`, 31,514,298 bytes. The zip is not committed.

## Gates

G0–G4 passed on that zip, then G5 was run again at generator commit `dc7ff66fba1a94fd761680849eb403214b18bd13` (this branch, cut from `origin/main`). `pipeline.json` is that G5 resume: 165.76 seconds, exit 0. The manifest holds all six PASS records. G5 rebuilds invsqrt, dqi and dfthcsos byte for byte. The only copied output is the declared factor. `shipping_problems()` is empty. No waiver.

```sh
TMPDIR=/home/cld-main/work/vqcc-data/pra309-chem-8-143-60/tmp \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 UV_NO_SYNC=1 PYTHONPATH=. \
  uv run python ledger/evidence/pra309-chem-8-143-60/run_candidate.py \
  --generator-commit dc7ff66fba1a94fd761680849eb403214b18bd13
```
