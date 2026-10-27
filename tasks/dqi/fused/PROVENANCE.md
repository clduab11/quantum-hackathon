# PRA-293 fused DQI decoder — vendored source

## Source

- Notebook: [`somejoint/quantum-circuits-21-34-local-gm-fused-dqi`](https://www.kaggle.com/code/somejoint/quantum-circuits-21-34-local-gm-fused-dqi), kernel 140675727, version 12, author Agniv Banerjee (SomeJoint team). Read anonymously (`kernels/pull`) on 2026-10-27 for PRA-202 (comment `3dca70e1`).
- UTF-8 source SHA-256 `18d6760953783bec316ddb46266a1b5ccc50c291fbf47ec35f87c73f4d0cf2ac`. Captured copy: `/home/cld-main/work/vqcc-data/pra202-pubmeasure-1027/source-check-1327/somejoint.src` (outside git).
- Licence: the notebook's credits cell says "the notebook code is Apache-2.0", and cell 6 embeds the full Apache-2.0 text (SHA-256 `cfc7749b…d523d30`, the same bytes as `../bm_forney/LICENSE`). No per-file SPDX headers.
- Design lineage (recorded, not gated): "rebuilt from scratch from a pseudocode description" of Alex Chilton's 883-qubit Schur decoder, itself based on jday96314's QuantumAI (no licence). Covered by the board's card `aba6c540` (option b), D-PRA269-01 and D-PRA273-01 (R-P2-6). Full credit chain: `NOTICE`.

## What was taken

Cell 6 holds 89 embedded files (`SOURCES`) with their SHA-256 (`SOURCE_HASHES`). They were extracted by AST literal parsing; the notebook was never executed. All 89 hashes matched. `EMBEDDED_FILES.json` lists all 89 with size, hash and whether they are vendored.

The build entry is `blocks/dqi/team-fused/source/exp/decoder/build.py`. Its closure was traced with a `sys.audit` hook during a full build: the entry script, the 53 modules it imports (54 Python files, 4,837 lines) and the 7 JSON layout files it opens (search outputs, read with `Path.read_text`). Those 61 files and `LICENSE` are copied **verbatim** under `source/` with the author's relative layout. `SOURCE_MAP.json` pins each one; every port hash equals its upstream hash and the author's own `source_sha256.json` pin.

Not taken: 27 embedded files outside the closure — the notebook launcher, packer and checkers (`notebooks/*`), the author's tests (`test_*.py`), unused variants, the README and `source_sha256.json`. No circuit, `.kmb`, `.npz`, notebook output, invsqrt or chemistry file is an input. The closure has no network, subprocess or file-write calls; `build.py` writes only its output path and a `.build.json` beside it.

## Why verbatim

The sources import each other through the author's `sys.path` layout (`from common import *`, bare `field`, `convert`, `scan`, and `exp.*` from the source root). Rewriting those imports is where a byte drift would come from, and it would make the audit harder. So `../generate_fused.py` checks every pin, then runs the unchanged `build.py` as a script in its own interpreter (`python -B`, scratch working directory), the way the author runs it, and moves only `dqi.kmb` to `--out`.

## Measured here

- Wrapper build in this worktree's venv (CPython 3.13.13, competition `kickmix.so` `c66b3216…5e`): `dqi.kmb` SHA-256 `7beea291a5de36ef2b4fb50585b2f8d7cce02d3c575b491cf5dcc93e9d9655f6`, 546,664,050 bytes, Q 889, static Toffoli-like 487,331, about 94 s, 2.19 GB peak RSS. This is the hash the notebook asserts.
- Verifier results, gates and the rebuild from a clean worktree: `ledger/evidence/pra293-fused/`.
