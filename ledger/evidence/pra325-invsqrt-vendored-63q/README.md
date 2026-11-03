# PRA-325: 63-qubit vendored invsqrt candidate

G0–G5 PASS on the exact zip at the fixed public salt and full official shot counts.
G5 rebuilt the committed generators using the declared, hash-pinned inputs, including
the licensed vendored circuit. `shipping_problems()` is empty.

| Task | Local ratio | Q | Full shots |
| --- | ---: | ---: | ---: |
| invsqrt | 20.056489329694145 | 63 | 200,540,928 |
| dqi | 54.72947182918558 | 889 | 102,400 |
| dfthcsos | 9.778169511363153 | 430 | 78,080 |

Local GM: **22.05859829244158**, up from submission-011's 19.205727125145224.
The result is local, not a Kaggle score. No upload occurred.

- Candidate: `pra325-invsqrt-vendored-63q`.
- Zip: `/home/cld-main/work/vqcc-data/pra325-invsqrt-vendored-63q/pra325-invsqrt-vendored-63q.zip`.
- Zip size: **31,542,030 bytes**.
- Zip SHA-256: `a0c0d32fa323b75f2d5d77bf2ef25456ac1d0d45850e65d86a1c880c7e2f64f4`.
- Parent: submission-011, `pra309-chem-8-143-60`, zip
  `a710cab21a8bac7ff552944ca48e8afb4e0fe4c98e0be5fd2e86be32b79c01ac`.
- Only `invsqrt.kmb` changed. All dqi and dfthcsos hashes equal the parent.
- Source: mrmeows dataset `qcc-1375-open-circuits` v8,
  `circuits/invsqrt.kmb`, SHA-256
  `0766a111a76f241aa57fbbed466436d743be13436943ddb0628c291ca07d67d6`.
- Apache-2.0 source acceptance: PRA-346 comment
  `1f89b270-3343-4d27-83b2-af6a7a9fc517`; retained in `source-acceptance.json`.
  See `tasks/invsqrt/vendored/PROVENANCE.md`, LICENSE, NOTICE, and SOURCE.json.
- Generator/vendoring implementation during G0–G4: commit
  `af8ffa6`; the rebased generator commit used by G5 is recorded in the manifest.
  This is an unchanged circuit copy under D-PRA341-01, not our own synthesis.

## Commands and results

```sh
uv sync
uv run python scripts/install_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation
uv run python -m tasks.invsqrt.vendored.generate --fetch --out /home/cld-main/work/vqcc-data/pra325-invsqrt-vendored-63q/staged
uv run pytest tests/test_invsqrt_vendored.py -q
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run pytest
uv run python -m ledger.registers check
TMPDIR=/home/cld-main/work/vqcc-data/pra325-invsqrt-vendored-63q/tmp OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=. uv run python ledger/evidence/pra325-invsqrt-vendored-63q/run_candidate.py --stop-after G4
uv run python scripts/merge_gate.py --ref mine=HEAD
uv run python scripts/merge_gate.py --pr 78 --ref mine=HEAD
```

- `uv sync` and pinned SDK installation: PASS.
- Focused tests: initially failed because the vendoring module did not exist;
  after implementation, **4 passed**. Tampered source is rejected without
  overwriting output; changed sibling-task hashes fail G4.
- Full suite: **496 passed, 11 skipped**, 317.38 seconds. Raw log: `pytest.txt`.
- Registers: initially rejected the notice's paragraph layout; fixed to bullets,
  then PASS (290 decisions, 8 notice files, legacy index unchanged).
- G0–G4: all PASS. `G3.json` contains official verifier summaries and hashes;
  `pipeline.json` and `g0-g4.txt` record the exact zip and gate results.
- Default merge-gate listing: could not run (anonymous GitHub API rate limit).
  The configured GitHub `list_pull_requests` tool returned the complete open
  set, #78 only. The explicit complete-queue command passed both orders at
  main `a04dc0a` and local head `7604172`; full output: `merge-gate.md`.
  This must be rerun on the final PR head after PRA-345 merges.

## G5 integration

After PRA-345 landed on main, the config declared the accepted source as
`vendored_circuit` with licence record PRA-346. The runner resumed the existing
G0–G4 manifest and ran real G5 on the same zip using persistent scratch:

```sh
TMPDIR=/home/cld-main/work/vqcc-data/pra325-invsqrt-vendored-63q/tmp OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=. uv run python ledger/evidence/pra325-invsqrt-vendored-63q/run_candidate.py
```

G5 PASS; `shipping_problems()` returned `[]`. G5 was then repeated successfully
on published generator commit `f4987444ac5b11ce485df40c871bc2df50404f21`;
the manifest retains both rebuild records and the original G0–G4 evidence.
The integrated suite passed (600 passed, 11 skipped), and the register check
passed. No upload occurred.
