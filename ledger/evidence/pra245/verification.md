# PRA-245 verification evidence

Runtime: Python 3.13.13 (uv venv), WSL, CPU (the verifier's numerical check; no fitting). Competition package at
`/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation`, unmodified:
`verifiers/dfthcsos/verify.py` 0775be7a528922367caebe9e4d051d6199811f1aefeaa4b793eaaa4621b8ec9d,
`verifiers/dfthcsos/scoreinfra/costs_prepare.py` 7f1e190c42fc5325f3e6689fbbef51f95b0cb12f1c828cda92b6c088e72206da
(the same hashes ViberTeam's `thc_verifier_full.json` lists).

## Fetch (read-only)

The Composio Kaggle connector (`KAGGLE_GET_DATASET_METADATA`, `KAGGLE_DATASET_LIST_FILES`, `KAGGLE_LIST_DATASETS`)
supplied the licence fields, descriptions, version numbers and file sizes. It then dropped out of the run
mid-download ("tool not found"). The bytes came from Kaggle's public, anonymous download endpoint
`https://www.kaggle.com/api/v1/datasets/download/<owner>/<slug>/<file>?datasetVersionNumber=<n>`. No token was
used, nothing was written to Kaggle, and no kernel or submission was run. Cross-checks: every size equals the
connector's file listing, and Gluzdov v4 equals ViberTeam's credited copy and the SHA-256 their notice publishes
(a29cb868…). Kaggle exposes no numeric `datasetVersionId` through the public API, so the pin is
datasetId + version number + SHA-256 (`ledger/manifests/inputs/pra245-thc-public.json`).

```text
$ sha256sum /home/cld-main/work/vqcc-data/inputs/thc/*.npz
a29cb868d59906bebcda50c1c44c14090d503665700d725027e25016544782fd  femoco_thc_r5.gluzdov-v4.npz
a0da3225ba2047f43ae24f31881f2a71500d3f73eda24fadc73e9f67da68e13f  femoco_thc_r5.gluzdov-v5.npz
1b97a9aec279618b9cf66f28960b3c85fae98d73dde31cd01febe2bc30352778  femoco_thc_r5.gluzdov-v6.npz
7db33b3eb951ac9c332aa4f7df8da106f9a7627e5b17a1c6f537e4f9b5e3084f  femoco_thc_r5.gluzdov-v7.npz
809a992900937425f01a0593803921873f7bb472d590592c378d3ceb23657df5  femoco_thc_r5.gluzdov-v8.npz
809a992900937425f01a0593803921873f7bb472d590592c378d3ceb23657df5  femoco_thc_r5.npz          (shipping copy)
141d368ebd6517d3875a38e4e416b4886adb1efc7bd3df901e69436a96af49a9  thc_selected_compact.viberteam-v2.npz
9b98b6284b2a846a6a8aa229f4c5a1da62aeba780b57c7341e49b8c3bfd53576  thc_submission.npz         (fallback copy)
9b98b6284b2a846a6a8aa229f4c5a1da62aeba780b57c7341e49b8c3bfd53576  thc_submission.viberteam-v2.npz
```

## Measurement

```text
$ uv run python ledger/evidence/pra245/measure_declared_factors.py --competition <package> \
    <thc>/femoco_thc_r5.gluzdov-v{4,5,6,7,8}.npz \
    <thc>/thc_submission.viberteam-v2.npz:<thc>/thc_selected_compact.viberteam-v2.npz > pra245-measure.json (summary committed as measurements.json)
exit=0 (about 60 s; stderr empty)
```

| file | SHA-256 | error1 mHa | error2 mHa | Lambda | E_gap Ha | lambda_eff | J | T | Q | ratio |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Gluzdov v4 | a29cb868… | 6.931189 | 19.989999 | 303.74824 | 3.914948811 | 48.610604 | 9 | 21570 | 822 | 3.8933 |
| Gluzdov v5 | a0da3225… | 6.717089 | 19.998748 | 297.83187 | 3.914913107 | 48.131541 | 9 | 21570 | 822 | 3.9320 |
| Gluzdov v6 | 1b97a9ae… | 6.383441 | 19.999497 | 294.45339 | 3.914898050 | 47.855862 | 9 | 21570 | 822 | 3.9547 |
| Gluzdov v7 | 7db33b3e… | 6.383441 | 19.999497 | 294.45332 | 3.914898050 | 47.855857 | 9 | 21570 | 822 | 3.9547 |
| **Gluzdov v8 (ship)** | 809a9929… | 6.383441 | 19.999497 | 294.45331 | 3.914898050 | 47.855856 | 9 | 21570 | 822 | **3.9547** |
| ViberTeam v2 (fallback) | 9b98b628… | 6.325973 | 19.999000 | 294.93633 | 3.914918000 | 47.895475 | 9 | 21570 | 822 | 3.9514 |

Every row passes `acceptance_problems` and `passes_accuracy` on the file's own words as shipped. All words lie in
[0, 2047], so reducing them mod 2^11 changes no word. ViberTeam's words decode exactly to its shipped `U`
(max |ΔU| = 0). Our ViberTeam row reproduces their published FULL-PASS metrics. Costs:
`heuristic_costs(76, 1, 496, 384, 11)` gives T 11,310, persistent 83, temporary 640. The ordinary-QROM ANGLE bound
uses 10 selection + 9 temporary + 11·J qubits ≤ 128, which gives J ≤ 9. This is an upper bound: ViberTeam's ANF
builder reaches J = 10 (T 20,286, Q 833, 4.146×).

## Tests and registers

```text
$ uv sync
Checked 36 packages
$ uv run python scripts/install_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation
Created: .venv/lib/python3.13/site-packages/vqcc_local.pth   (fresh worktree; without it 5 kickmix tests fail on import)
$ uv run pytest -q
315 passed, 1 skipped in 79.33s
$ uv run python -m ledger.registers check
OK registers: 236 decisions, 6 notice files, legacy index unchanged
```

No lint tool is configured in this repository.
