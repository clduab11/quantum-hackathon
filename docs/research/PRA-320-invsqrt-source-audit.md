# PRA-320: mrmeows v6 and v8 invsqrt source audit

No inspected release provides a closed source-plus-numeric-table build under
PRA-320's R10 rules. The v6 63-qubit generator, v8 19.945× front38 generator,
v8 19.80× history package, and v8 20.0565× generator all consume frozen circuits
and synthesis records. The included earlier builders do not close that chain.
No `pra309-invsqrt-63q` candidate was created. This is a negative result for a
direct port of these release pipelines, not proof that a new implementation of
the architecture cannot reach 20×. A sub-20× port was considered and rejected
for the same input dependencies, not for missing the score target.

## Source identity and licence

Sources: [mrmeows v6](https://www.kaggle.com/datasets/mrmeows/qcc-1375-open-circuits/versions/6)
and [mrmeows v8](https://www.kaggle.com/datasets/mrmeows/qcc-1375-open-circuits/versions/8),
Apache-2.0. Both downloaded LICENSE files have SHA-256
`cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`;
the text is preserved in `ledger/evidence/pra320-source-audit/LICENSE`.
Version 8 was the latest reported in the original 2026-10-28 metadata query.
The continuation explicitly requested `datasetVersionNumber=6` for the older
`source/invsqrt_63q/` path, which does not occur in the v8 inventory.

Evidence under `ledger/evidence/pra320-source-audit/`:

- `SOURCE_MAP.json`: original 143 v8 source/document/configuration hashes;
  `PACKAGE_INDEX.json`: original selected 20p056 package's 644-file inventory.
- `ADDITIONAL_SOURCE_MAP.json`: 363 additional source/document/configuration
  files, fetched anonymously with version-specific URLs on 2026-10-29. Every
  downloaded file is pinned by SHA-256, byte size, version and URL. Source
  stays outside git. The v6 README.txt hash matches the PRA-285 reference.
- `v6-63q-PACKAGE_INDEX.json`, `v8-19p945-PACKAGE_INDEX.json`,
  `v8-19p80-PACKAGE_INDEX.json`: complete selected-package filename/size
  inventories. The v6 listing was paginated to completion (921 dataset files).
- `frozen-inputs.json`: per-package dependency tables and upstream hash pins,
  including all baseline config pins and explicit checks of missing L5 inputs.
  These are evidence, never declared generator inputs.
- `source-only-rebuild.json` and `additional-source-only-rebuilds.json`:
  actual entry-point commands, exit codes and tracebacks.

Only source, documentation and configuration were fetched for the extension.
No `.kmx`, `.kmb`, native SDK, synthesis certificate, proof or angle replay was
fetched. A 429 response during the first batch stopped that fetch; the resumed
fetch reused completed files and used sequential requests with a delay. No
Kaggle credential or upload was used.

## v6: source/invsqrt_63q/

The package README reports Q63 and 19.130134273194× for its 28-stage release.
That is upstream evidence, not a new fixed-salt measurement by us.
Paths in this table are relative to `source/invsqrt_63q/`.

| Entry point / stage | Required input | Finding |
| --- | --- | --- |
| `generate.py:24-26` | `build_config.json`, all `frozen_inputs` | Hash-checks frozen inputs before running any stage. |
| `build_config.json`, stage 01 `round6_arithmetic/regroup_low_outer.py` | `round5_phase/l6_exact.logical.kmx` | Starts from a circuit checkpoint, SHA `a98ed6cfbddda86aa6f560605d965339e404170bca3d51f02839286956a31eb5`. |
| Stages 02–28 | 16 further pinned synthesis/proof records | Full 17-entry circuit/record list and all 82 config pins are in `frozen-inputs.json` under `v6-63q`. These include lookup, shared decoder, cache, overlap and pool39 records. |
| Earlier `round5_phase/l6_exact.py:26-30,125-168` | L5 circuit, build report, relation record, L4 decoder certificate; also `late_lword_probe.json` | Four inputs are absent from the full package inventory; see the common ancestor section. The probe JSON is listed upstream but was not fetched. |
| `round4_root/build_shared_address.py:15-28` | `radical_norm/both_reflect76.kmb` and synthesis records | The plausible L5 builder still starts from a frozen reflected circuit and demands an exact circuit-text hash; accepting a filename argument does not remove that dependency. |

The source-only invocation exits **1** on the stage-01 circuit before simulation.
The v6 path is therefore checked directly, rather than inferred from v8.

## v8: sources/invsqrt_19p945_front38_source/

Package root: `invsqrt_verified_10412405_front38/`. Its README reports Q63,
19.945192422498× and 200,540,928 shots. Those are upstream numbers only.

| Entry point / stage | Required input | Finding |
| --- | --- | --- |
| `generate.py:11` | `source/invsqrt.kmx` | Mandatory circuit hash `77302e018eff451da70fc521f28630c27881ea83741a958618c81a9ea0f90bc5`. |
| `compiler/build_partial_merge.py:51-83` | The same circuit; `data/phase_features.json`, `data/partial_merge3_fit.json`, `data/high_table.json` | Re-extracts Boolean features from the circuit, but replays saved angles and fit deltas. A high-word numeric table alone cannot close this chain. |
| `compiler/replay_history.py:11-13` | `compiler/history_replay_records.json` | Replays selected rewrites and verifies them against the circuit. |
| `generate.py:20-23`; `compiler/replay_frontier_component.py:60-100` | `proofs/frozen_front.block.kmx`, `compiler/frozen_front.json` | Frozen circuit block plus a decoder/measurement-repair certificate. Replaying and checking a selected network is not synthesizing it from numeric inputs. |
| `source/generate.py:28-32` | `source/baseline/invsqrt.kmx`, `source/lookup_certificate.json.gz`, `source/curvature_certificate.json` | Two-stage replay of the frozen 32-stage ancestor. |
| `source/baseline/generate.py` | Baseline config's 35 frozen circuit/proof inputs | Starts from the same L6 checkpoint and reaches the same unresolved L5 dependencies. |

The source-only invocation exits **1** on `source/invsqrt.kmx`. This release
was not passed over merely because 19.945× is below 20×: its input chain fails
R10 independently of score.

## v8: sources/invsqrt_19p80_history_cache_research/

Package root: `invsqrt_history_research/`. Its README distinguishes the recovered
Q63 baseline (19.8014241068×) from a new Q64 research candidate, rejected on
modeled total cost and not given a new full official verification.

| Entry point / stage | Required input | Finding |
| --- | --- | --- |
| `build.py:7-8`, `PINS.json` | `baseline/invsqrt.kmx` and `baseline/invsqrt.kmb` | Pins both frozen baseline circuits before invoking the history search. |
| `tools/phase_history.py:27-36` | `baseline/invsqrt.kmx` | Reads the frozen baseline even when an alternate input needs its suffix. The top-level output is the rejected Q64 candidate. |
| `baseline/generate.py:11` | `baseline/source/invsqrt.kmx` | The potentially useful Q63 baseline also begins from circuit hash `77302e…90bc5`. |
| `baseline/compiler/build_partial_merge.py`, `replay_history.py` | Saved phase features/fit deltas, high-word table, history-replay records | Same phase/history input categories as front38; no numeric-only entry point. |
| `baseline/source/generate.py` | `baseline/source/baseline/invsqrt.kmx` and lookup/curvature certificates | Replays the same two frozen-checkpoint stages. |
| `baseline/source/baseline/generate.py` | 35 frozen circuit/proof inputs in the 32-stage config | Same L6 checkpoint and missing L5 chain. |

Both the top-level builder and the Q63 baseline generator were invoked with
source/config only. Both exit **1** on their first missing frozen circuit.

## v8: sources/invsqrt_20p056_verified_source/

Package root: `invsqrt_20p056505_complete/`. Let `A` mean
`provenance/invsqrt_20.032119x_verified/invsqrt_20.032119x_verified/`.
This preserves the original audit; no repeated numerical run was needed.

| Entry point | Required input | Finding |
| --- | --- | --- |
| `generate.py` | `input/recovered_20p032119.kmx` | Hash-checks and rewrites two five-Toffoli blocks in a frozen circuit. |
| `generate.py --replay-upstream` | `provenance/invsqrt_20.032119x_verified.zip` | Delegates to the inherited replay; the expanded archive is present in the inventory. |

### 20p032 verified ancestor A

| Entry point | Required input | Finding |
| --- | --- | --- |
| `A/generate.py` | `source/invsqrt.kmx`, `proofs/frozen_front.block.kmx`, `compiler/frozen_front.json`, saved phase fits | Replays selected transforms of frozen circuits. |
| `A/source/generate.py` | `baseline/invsqrt.kmx`, `lookup_certificate.json.gz`, `curvature_certificate.json` | Two-stage checkpoint replay. |
| `A/source/baseline/generate.py` | 35 circuit/proof dependencies in `build_config.json` | The 32-stage replay starts at `round5_phase/l6_exact.logical.kmx`. |
| `A/source/baseline/round5_phase/l6_exact.py` | L5 circuit and build/decoder records | The same four missing dependencies below. |

The original source-only 20p056 invocation exited **1** at
`input/recovered_20p032119.kmx`. This is a dependency failure, not G5 or a verifier
result. Do not supply forbidden frozen inputs to turn these probes into PASS.

## Common earlier chain and the numeric-table alternative

All three newly inspected baseline configs start from the same L6 circuit hash.
Their included `round5_phase/l6_exact.py` needs these four files, relative to
its baseline root, absent in each complete selected-package inventory:

- `round4_root/l5_shared51_late25_build/phasepark.logical.kmx`
- `round4_root/l5_shared51_late25.logical_build.json`
- `round3_root/l5/extra.json`
- `round5_arithmetic/two_shift_lateL.logical.certificate.json`

The L6 source can regenerate some exact quadratic decoders, but it first needs
that L5 circuit and its synthesis records. We followed the included plausible
L5 producer, `round4_root/build_shared_address.py`, rather than treating a
missing output as proof that no producer exists. It reads
`radical_norm/both_reflect76.kmb`, checks circuit-text SHA-256
`5f318ffb470e37f2b6225444dbccc4572858cde400bc004bb0e4d1223ac09e20`, and also
requires `radical_newton/address_helper_scratch.json`,
`round3_root/l5/{extra,early,late}.json`, `round3_memory/l4_direct.json`, and
`round4_root/address_joint.json` (via `shared_address.py`). Its input circuit
and selected records are not replaced by a coefficient table. Included
reflection passes transform an input circuit; they do not resolve this root.

There is useful original arithmetic/fit code, including
`radical_newton/signed_digit_helpers.py`, credited to
[Sumit Chongder's v2 notebook](https://www.kaggle.com/code/sumitchongder/notebook2f196e646b),
Apache-2.0 as stated in its header. Its coefficient fitter does not supply the
missing selected L5 circuit, decoder networks, and subsequent phase records.
The later front38 builder reads `angles_turns` and `delta_scaled`; the 20p032
phase builder reads saved `angles_turn_units64`. Regenerating coefficients
alone is therefore insufficient. No complete release chain using source and
only non-circuit numeric tables was found, and no input was declared under
D-PRA211-05. Implementing fresh synthesis and fitting around this architecture
remains possible, but is a new compiler project rather than the audited port.

## Best verified point

The fresh incumbent result is `pra294-c59`, invsqrt
**13.237727705632725×**, Q **84**, all **200,540,928** shots PASS at
`PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`, circuit SHA-256
`17fc223d79d3f1f15ef448389072209972b373403dd0a45352f4fe7eaff541ad`.
The earlier 13.237730853850163× number belongs to the PRA-285 caine circuit
`6858074b…bb57f`; it is not this fresh measurement.

| Task | Q | Fresh ratio | Verified shots |
| --- | ---: | ---: | ---: |
| invsqrt | 84 | 13.237727705632725 | 200,540,928 |
| dqi | 889 | 54.72947182918558 | 102,400 |
| dfthcsos | 423 | 8.589916214949021 | 87,424 |

All three passed in the already-completed `harness/score_local.py` run. GM:
**18.39393056697713**. Incumbent zip SHA-256:
`f569b107f4136d388636bcdb03f323b5c7483df463a3f8b6d682624de97e7435`;
size **31,809,317 bytes**. `incumbent-score.jsonl`,
`incumbent-invsqrt-recheck.json`, and `audit-checks.json` preserve the evidence.
The incumbent manifest's existing `shipping_problems() == []` belongs only to
that incumbent. It is not a new G0–G5 claim.

No new circuit or zip was produced. The requested ≥20× / Q≤63 / GM≥21 result
was not achieved. No candidate G0–G5, shipping clearance, or Kaggle upload is
claimed. John-wick owns review and the next scope decision: a source-complete
earlier chain or a fresh compiler with regenerated synthesis and phase fits.
No R10 exception is requested.

## Isolation and verification

The separate-worktree approval was accepted on 2026-10-29. The new branch
`op-vqcc/pra320-source-audit` was cut from current `origin/main`
`c7ca465` in `/home/cld-main/work/qh-pra320`. The 15 saved PRA-320 files were
copied only after checking their handoff hashes. No shared-branch file, commit,
or other task's change was modified. D-PRA320-01 was still an uncommitted draft;
its correction does not amend an accepted decision.

The original shared-tree run (440 passed, 12 skipped, 4 failed) and its merge
gate remain preserved as historical diagnostics in `pytest.log` and
`shared-branch-merge-gate.md`; neither validates this branch. The first isolated
run failed seven subprocess imports because its new venv lacked the local
Kickmix path. The repository installer added the hash-checked supplied SDK to
this worktree's venv; no tracked source or dependency version changed.

The isolated suite passes: **424 passed, 11 skipped**; `uv sync` and
`uv run python -m ledger.registers check` exit 0. Results are recorded in
`isolated-checks.json`. The open-queue merge gate fails: PR #74 conflicts with
main in `docs/decisions/D-PRA304-01.md`, in every tested order (120/120 on the
first committed audit head). The full report for the handoff head is pasted
in the PR body. This audit is a draft for review, **not merge-ready**. John-wick
must route #74 to its author for resolution and rerun the whole queue before
readiness; no other task's register entry is changed here.
The source-only probes are expected failures on forbidden inputs, not tests of
the mathematical architecture. No new numerical candidate was available to
verify or gate.
