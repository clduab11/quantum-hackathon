# PRA-236 paired-v6 verification

The first port meets the **23x floor**: **23.555494474x**, at Q 881, executed T 1116994.2602050782, 0 value errors and 1 phase error over 102,400 fixed-salt shots. The 28x target is not met.

## Identity

- Repository: `clduab11/quantum-hackathon`.
- Branch: `op-vqcc/PRA-236-dqi-compression`; inherited planning worktree unchanged.
- Published generator: `905794dbbac4528b603f5254f34e4b82f9a373bd`.
- Source tree: `d4a4c28616c9ff6839d4da8ab7d65d358d039616`, identical locally and on GitHub.
- PR: https://github.com/clduab11/quantum-hackathon/pull/33.
- Candidate: `pra233-2-dqi-q881`.
- DQI SHA-256: `dec77920d4b9f5964b6cd52c947aa0c91468d56b7ed28cd475fdfc18d067729d`.
- Exact zip SHA-256: `9498078459176333dc05c8bf1ec8538134afd9fea1b937caf59a0133882492d3`; 107,550,448 bytes.
- Durable path: `/home/cld-main/work/vqcc-data/queue/pra233-2-dqi-q881.zip`.

## Change and design decisions

Port the approved SomeJoint / Phuc Thai / ViberTeam J-fraction lineage, fixed to paired-v6. Reuse the syndrome bank, two gap pointers and norm-recycled inverse workspace. Write a new Lagrange-interpolation / field-trace projection from Manwithacat's mathematical method. The original projection file is not copied or transliterated; this is not a strict clean room because the original was read. Preserve all applicable Apache-2.0 text and NOTICE lines. See D-PRA236-01/02 and `tasks/dqi/jfraction/PROVENANCE.md`.

Engineering lenses: **Boundaries over internals** fixed the source-only generator contract; **No new hidden state** removes notebook path discovery and module monkey-patching; **Test the failure first** established the projection tests before implementation; **Say what you did not check** separates sampled correctness, restricted rebuild, legal review and upload.

Only standard Python and Kickmix are needed for the DQI generator. No input circuit, verify-only path, Kaggle wrapper, salt or mixed-portfolio dependency is in that generator. The existing BM generator is retained. The invsqrt and dfthcsos output members are unchanged from the existing approved portfolio; no unrelated refactor was made.

## Full DQI measurement

Command (exit 0):

```sh
OMP_NUM_THREADS=1 uv run python /tmp/pra236-logs/verify_dqi.py
```

The captured script is included beside this report. It loads only our generated `/tmp/pra236-build/dqi.kmb` and calls the official verifier with `ProblemSpecDQI.benchmark_instance()`, `salt='PRA171_LOCAL_PUBLIC_FIXED_SALT_0001'`, `seed=None`, `max_workers=1`. Output:

```json
{
  "status": "PASS",
  "verified_shots": 102400,
  "value_errors": 0,
  "phase_errors": 1,
  "num_qubits": 881,
  "toffoli_count": 1116994.2602050782,
  "max_toffoli_count": 1147675,
  "effective_error_rate": 0.0009104197583220583,
  "repetition_factor": 1.1967314991687559,
  "score": 1037527174785.328,
  "circuit_sha256": "dec77920d4b9f5964b6cd52c947aa0c91468d56b7ed28cd475fdfc18d067729d",
  "wall_seconds": 389.4901082389988
}
```

Reference cost: 24,439,465,632,206.816. Epsilon-plus is at log2(delta)=-128. Static T is not the executed scoring count. No second salt or seed selection was used. The exact-zip G3 log is separately retained by the gate runner.

## Tests

`uv sync`: exit 0, CPython 3.13.13 environment synchronized. Repository Kickmix installer configured the provided package. Baseline before the port: `uv run pytest -q` -> `275 passed, 1 skipped in 200.34s`.

Before implementation, `uv run pytest -q tests/test_dqi_projection.py` exited 2 with `ModuleNotFoundError: No module named 'tasks.dqi.jfraction'`. After implementation:

```text
$ uv run pytest -q
281 passed, 1 skipped in 128.72s (0:02:08)
$ uv run pytest -q tests/test_dqi_projection.py tests/test_dqi_jfraction.py
7 passed in 8.84s
```

The second command includes the source-map regression added after full-suite collection and the final removal of the unused alternate driver. Tests cover the phase identity for every field position and basis error, an emitted projection circuit with dirty reused scratch, zero/nonzero inverse values and HMR cleanup, and declared source hash identity. Logs are retained alongside this report. No pre-existing test failure was found; the existing skip remains: `tests/test_run_notebook.py:8` cannot import optional `nbformat` (`No module named 'nbformat'`). No notebook run is claimed; the DQI driver itself needs only standard Python and Kickmix.

## Exact-zip gates

Command (exit 0):

```sh
OMP_NUM_THREADS=1 uv run python -m ledger.gates.runner run --manifest ledger/manifests/candidates/pra233-2-dqi-q881.json --zip /home/cld-main/work/vqcc-data/queue/pra233-2-dqi-q881.zip --config configs/gates/pra236-jfraction.yaml
```

Actual output:

```text
G0 PASS
G1 PASS
G2 PASS
G3 PASS
G4 PASS
G5 PASS
shipping_problems() []
```

All gates bind the exact zip above; none was waived. G3 full shots: invsqrt 200,540,928 (0 failures, ratio 13.16480863637127), DQI 102,400 (0 value / 1 phase error, ratio 23.55549447392886), dfthcsos 254,464 (verifier PASS, ratio 0.9999999999999997). **Geometric mean 6.76865313085382**, above the parent 5.721389477411993 and archive best 5.721389477411995. G3 raw evidence is `G3.json`, SHA-256 `a4350175a1d4d7c3f02bee73ef3f1352b86324cc71f484bb6fc213d1587240d5`.

G5 checked out published generator commit `905794dbbac4528b603f5254f34e4b82f9a373bd` in a clean detached worktree. Every generator returned 0; every file was identical, with no missing, extra or changed files. Only declared input `sample_submission/dfthcsos/submission.npz` (SHA-256 `14d5cc25eb3bf82a9ccb87c811db28d127bef6d28697dd190dc1e875de3bfe69`) was staged. The only copied non-circuit was that factorization, permitted by D-PRA211-05. **DQI had no declared input and no copied output.** G5's complete command/return-code record is in the candidate manifest. No public DQI binary was read or shipped.

## Allocation evidence

`uv run python ledger/evidence/pra233-2-dqi-q881/phase_profile.py /tmp/pra236-profile.kmb` exited 0 and reproduced the DQI SHA-256 exactly. The probe enforces the native allocation cap at 881 and samples explicit Python allocation/free boundaries. Thus observed peaks of 881 are exact; lower observations remain bounded intervals because a native operation may allocate transient internal scratch.

| Phase | Observed peak | Native upper bound | Live at end | Cumulative ID highwater | Static T in phase |
|---|---:|---:|---:|---:|---:|
| initialization | 852 | 881 | 852 | 840 | 0 |
| moment_to_fraction | 881 | 881 | 852 | 881 | 320804 |
| fraction_to_polynomials | 877 | 881 | 852 | 881 | 78996 |
| phase_correction | 881 | 881 | 852 | 881 | 348075 |
| polynomials_to_fraction | 877 | 881 | 852 | 881 | 78996 |
| fraction_to_moments | 881 | 881 | 840 | 881 | 320804 |

All three costly phases now fit Q 881 together. The 12 unreferenced gap-pointer qubits at initialization explain live count 852 while the referenced-ID highwater is still 840. The probe neither changes allocator order nor the emitted circuit. This is allocation evidence, separate from the restricted-input G5 rebuild.

## Honest boundary

The inherited decoder is approximate for three or more first-order gaps and higher-order gaps. A 102,400-shot pass does not establish zero true error. No hidden-salt Kaggle score or notebook execution is claimed. John Wick owns uploads; Chris owns merges; The Adjudicator owns machine/live-stack sign-off. No live system, production configuration, main branch or uploaded submission was changed. The original projection licence interpretation is still for the Adjudicator; this port uses new projection code under John's accepted scope.
