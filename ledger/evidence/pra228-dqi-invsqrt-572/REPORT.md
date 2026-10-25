# PRA-228 verified bundle

The rebuilt zip is byte-identical to the historical 5.72x bundle. The measured local geometric mean is **5.721389477411993** on the fixed public salt. G0, G1, G2, G3 and G5 passed. G4 is **WAIVED**, with its real FAIL retained. No Kaggle upload or private-salt score is claimed. The single pytest skip is the optional notebook module (`nbformat`/`nbclient`/`ipykernel` dependency group), not a circuit-verification skip.

- Branch: `op-vqcc/pra228-572-bundle`.
- Generator commit: `562663a62327ce4d81fdea7d5949ff39ce7667c3` (published main; clean when the manifest was created).
- Candidate: `ledger/manifests/candidates/pra228-dqi-invsqrt-572.json`.
- Parent: `submission-001` (measured 1.0; kind `submission`).
- Config: `configs/gates/default.yaml`, unchanged.
- Salt: `PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`; no salt/seed sweep.
- Durable queue zip: `/home/cld-main/work/vqcc-data/queue/pra228-dqi-invsqrt-572.zip`.
- SHA-256: `b6709a4692802091f169332630ef54f0c0d9ffe3a6bcd26179e278c2189975ba`.
- Size: **91,399,451 bytes**. Both size and SHA-256 equal the historical artifact.
- `shipping_problems()`: `[]`.
- Generator/archive runtime: 222.969 seconds. Manifest creation through final G5: 585.675 seconds (2026-10-25T07:43:07.628558+00:00 to 2026-10-25T07:52:53.303940+00:00).

## Results

| Task | Measured ratio | Full shots | Failures | Qubits |
| --- | ---: | ---: | ---: | ---: |
| dfthcsos | 0.9999999999999997 | 254,464 | not reported | 730 |
| dqi | 14.22623531711937 | 102,400 | 3 | 1789 |
| invsqrt | 13.16480863637127 | 200,540,928 | 0 | 90 |

DQI has 0 value errors and 3 phase errors. invsqrt has 0 failures. dfthcsos has no aggregate failure counter (`null`); its verifier returned PASS at all 254,464 configured shots. The structured verifier summaries are in `G3.json`, whose SHA-256 is recorded in the candidate manifest.

```text
G0 PASS
G1 PASS
G2 PASS
G3 PASS
G4 FAIL parent submission-001 has no measured geometric mean in the ledger
G4 WAIVED PRA-228 step 3 permits a G4 waiver when real PASS is unavailable. The real FAIL is retained: G4 searches parent only among kind=candidate and cannot resolve mandated submission-001 (kind=submission). Independent g4-comparison.json verifies measured 5.721389477411993 > parent 1.0. The archive best pra197-dqi-bm-forney is the identical zip with all 13 identical hashes and historical score 5.721389477411995; current dfthcsos ratio 0.9999999999999997 accounts for a -1.7763568394002505e-15 geometric-mean difference. Strict archive improvement is unavailable for this byte-identical rebuild. No gate, generator, parent, or archive record was changed. D-PRA228-01 authorizes this lineage; D-PRA220-01 stays on record. G4 is WAIVED, not PASS.
G5 PASS
shipping_problems() == []
```

G4's unchanged implementation (`ledger/gates/checks.py:106-122`) filters parent lookup to candidate manifests, so it cannot find `submission-001`. It also requires a strict improvement over the already archived `pra197-dqi-bm-forney`, whose zip and task hashes are identical; historical geometric mean is 5.721389477411995. `g4-comparison.json` independently verifies the actual geometric mean 5.721389477411993 > 1.0, all file hashes equal the archive, and a score difference of -1.7763568394002505e-15 from its historical 5.721389477411995. The dfthcsos ratio is 0.9999999999999997; invsqrt and dqi exactly match the targets. Actual values are preserved, not rounded to the target. The waiver uses the fallback expressly allowed by task step 3. No archive was hidden or edited, and no gate was changed. This is not an all-six-PASS result.

G5 checked out the published generator commit into a clean disposable worktree and regenerated all three tasks against only the declared input. All 13 file hashes match with no missing, changed or extra files. The only copied file is the declared non-circuit dfthcsos `.npz`, under D-PRA211-05. Its SHA-256 is pinned in the unchanged config. No circuit binary was supplied as a generator input.

## Exact file hashes

All 13 hashes were checked before any gate; DQI size is 823,297,489 bytes.

| Zip member | SHA-256 |
| --- | --- |
| `dfthcsos/angle_k_0.kmb` | `7bfb3983accc6ff97d6ab41a88deae924f1d1c97cf30e60879d0bff5688a8e25` |
| `dfthcsos/angle_k_1.kmb` | `a04b6d0d57ce851b123af265066aaab2ab33353ea049d26acd534727466d72b6` |
| `dfthcsos/angle_k_2.kmb` | `5c1b8987bc3fa1a4b8607e470f8c8f1392c22e7a7dbcb228f0ce9ec986e18058` |
| `dfthcsos/angle_k_3.kmb` | `16ac67cdcaf3e2c6abdd98c4138ff1ae8a56cfc4ae15622bcdb3d3a3ba1e22cf` |
| `dfthcsos/angle_k_4.kmb` | `d21cdd4c7e94196654aab15ebcabfe10ce8d343151a5e8dc3672e76684b6628d` |
| `dfthcsos/angle_k_5.kmb` | `63b8d4cba36955e6098321f3b2ef3e34401dd276fa629b2e490d043b1743880b` |
| `dfthcsos/angle_k_6.kmb` | `5bf740428e661d035fda860142578f421969e35e0df2e4e024fbf01a7340b378` |
| `dfthcsos/angle_k_7.kmb` | `606009582111a22bd549b795c8d115ac8bbeb124bc8da24a80380eca6d34163d` |
| `dfthcsos/angle_k_8.kmb` | `57c7cc51f5922fff6e95d76e1f723d4c2d029a241da643b95684d6322157a8fe` |
| `dfthcsos/angle_k_9.kmb` | `22cbe2828988ff954fc07fd971a25e6bc04a02c302bf2cc642e4c3535daaad65` |
| `dfthcsos/submission.npz` | `14d5cc25eb3bf82a9ccb87c811db28d127bef6d28697dd190dc1e875de3bfe69` |
| `dqi.kmb` | `529b075009f7758abeda83a63407f0c1feeb51dd70631ae4335dfd28721b7e08` |
| `invsqrt.kmb` | `75e8a0e2341bb3e8f8ded1ec1d53e24437410c69e887da9daf7d49bfcc28c2dd` |

## Commands and output

From `/home/cld-main/work/.paperclip-worktrees/quantum-hackathon/pra228-572-bundle`:

```text
$ uv sync
Resolved 50 packages in 1ms
Installed 12 packages in 50ms
(exit 0)
$ uv run python scripts/install_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation
kickmix 0.1 /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation/kickmix/kickmix.so
Created: /home/cld-main/work/.paperclip-worktrees/quantum-hackathon/pra228-572-bundle/.venv/lib/python3.13/site-packages/vqcc_local.pth
(exit 0)
$ uv run pytest -q
........................................................................ [ 32%]
........................................................................ [ 64%]
........................................................................ [ 97%]
......                                                                   [100%]
222 passed, 1 skipped in 66.84s (0:01:06)
(exit 0)
$ uv run python -m ledger.registers check
OK registers: 100 decisions, 4 notice files, legacy index unchanged
(exit 0; baseline)
```

Build commands (each exit 0; `OMP_NUM_THREADS=1`):

```sh
uv run python tasks/invsqrt/generate.py --out /home/cld-main/work/vqcc-data/pra228-572-build/generated
uv run python tasks/dqi/generate.py --out /home/cld-main/work/vqcc-data/pra228-572-build/generated
uv run python tasks/dfthcsos/generate.py --out /home/cld-main/work/vqcc-data/pra228-572-build/generated
```

`ledger.archive.build_zip` made the deterministic archive. `ledger.gates.runner.start_candidate` created the candidate with parent `submission-001`, provenance recorded in the manifest, and the fixed public salt. The unmodified runner command was:

```sh
OMP_NUM_THREADS=1 uv run python -m ledger.gates.runner run --manifest ledger/manifests/candidates/pra228-dqi-invsqrt-572.json --zip /home/cld-main/work/vqcc-data/pra228-572-build/pra228-dqi-invsqrt-572.zip --config configs/gates/default.yaml
```

It exited 1 at real G4 FAIL after G0–G3 PASS. The same command was resumed with `--waive 'G4=<reason recorded verbatim in the manifest>'`; it exited 0 after G4 WAIVED and G5 PASS. Logs are `gates-initial.log` and `gates-g5.log`. Build logs and measured times are alongside this report.

## Provenance, scope and rollback

D-PRA228-01 records the board ruling and its accepted residual risk. The invsqrt lineage remains `regenerated; dataset-adapted calibration; licence unresolved`; D-PRA220-01 remains on record and PRA-223 continues. Apache-2.0 in the manifest identifies the notebook code parents, not a licence grant for disputed calibration rights. No PRA-224 refusal was added.

This branch adds only new decision rows, one candidate, its evidence, and its queue pointer. Existing source, generators, configs, tests, historical manifests, notices and decisions are unchanged. There is no new behavior requiring a regression test; the existing suite, fresh generation, fixed-byte checks, full verifiers, and clean G5 rebuild validate this artifact.

This is a local verifier result, not a prediction of Kaggle's secret-salt score. Only John Wick can reserve and upload. Caine did not reserve a slot, upload, merge or push main. The inherited PRA-193 worktree remains unchanged. To withdraw this candidate, stop its upload and add a superseding decision/withdrawal record; preserve all historical evidence and append-only decision rows. Do not blindly revert decision files.

## Final suite and register check

```text
$ uv run pytest -q
........................................................................ [ 32%]
........................................................................ [ 64%]
........................................................................ [ 97%]
......                                                                   [100%]
222 passed, 1 skipped in 72.04s (0:01:12)
(exit 0)
$ uv run python -m ledger.registers check
OK registers: 102 decisions, 4 notice files, legacy index unchanged
(exit 0)
```

The merge-order gate is run on the final commit; its exact report is attached to the Paperclip ticket and pasted into the PR body. The 91,399,451-byte zip exceeds Paperclip's 10 MB attachment limit (HTTP 422), so the requested durable queue path is the binary handoff. The report and evidence logs are published separately.
