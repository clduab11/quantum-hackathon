# PRA-197 allocation experiment and published G5 repair

The default decoder is unchanged. Retain `pra197-dqi-bm-forney`: Q 1789,
executed Toffolis 445229.0, fixed-salt ratio 14.22623531711937.
The 20-30x stretch was not reached. No candidate was queued or submitted.

## Resource hypothesis and result

The existing allocator already reuses freed IDs. Native allocation profiling
finds tied 1789-qubit peaks in BM rounds 66-68, Euclid replay and reverse BM.
Logical live counts at phase entry are not native peak allocation counts.

The compact64 experiment uses the existing `compact_quotient` from BM round 64
onward. It reduces the round-66 peak to 1777, but round 68, Euclid replay and
reverse BM still hit 1789. Static and executed Toffolis increase by 342.
Changing only one phase cannot reduce max referenced qubit ID + 1.
No decoder windows, salts, support assumptions or default generator were changed.

The probe source is `ledger/evidence/pra197-compact64/allocation_probe.py`.
It wraps allocation emission without changing the baseline circuit. Its baseline
build matched the prior artifact SHA-256 byte-for-byte. `allocations.json` holds
selected native peak snapshots; `allocation_id_at_peak` is the wire allocated at
that snapshot, not a global maximum ID. The circuit's Q supplies the latter.

Reproduce from repository root, with the documented kickmix environment:

```sh
OMP_NUM_THREADS=1 PYTHONHASHSEED=0 uv run python ledger/evidence/pra197-compact64/allocation_probe.py /tmp/pra197-baseline
OMP_NUM_THREADS=1 PYTHONHASHSEED=0 uv run python ledger/evidence/pra197-compact64/allocation_probe.py /tmp/pra197-compact64 64
```

`--out` is not a probe argument: these are positional output directories.
The default generator retains its original `--out` contract and gate hooks.
The probe writes a circuit and a profile. Only the circuit goes into the test ZIP.
Probe code pin: published `2e0564d65edcb30291a474e478502a60eaa64b24`, tree
`ac1d3c626ccaa000df3ea597c2bcf08f1b2fa0f9`, equal to local `393bc73`.

## Full verification of the rejected experiment

Candidate `pra197-compact64`, parent `pra197-dqi-bm-forney`.
G0-G3 PASS; G4 **FAIL**: 5.678948 does not beat parent 5.721389.
Same fixed public salt `PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`.

| Measurement | compact64 |
| --- | ---: |
| Shots | 102400 |
| Q | 1789 |
| Executed Toffolis | 445571.0 |
| Value errors | 0 |
| Phase errors | 11 |
| epsilon+ | 0.001213859080837334 |
| R | 1.2318701004651693 |
| Cost | 1756719865503.6814 |
| Ratio | 13.911987968098492 |
| Three-task geometric mean | 5.678948295901219 |

Full three-task summaries are in `ledger/evidence/pra197-compact64/G3.json`.
The candidate was created by `uv run python -m ledger.gates.runner new` with
`--parent pra197-dqi-bm-forney`. Individual `run_gate` calls evaluated G0 through
G4; the automatic enqueue pipeline was not called.

Experimental dqi SHA-256 `ef9b40df92c49305d1db7b948050f50319237dea557f0d18b37e301ce912b0cd`,
823532055 bytes. ZIP SHA-256 `2b4de49492b4a29259b84b09c8129b6d17e1f5d8f930c03040db905957d95180`,
91502360 bytes. Neither binary is committed.
G2 used 1536 shots; its PASS is not parity. No G5 or three-salt diagnostic was
run for compact64 because it is not selected and will not be queued.

## Reproducibility repair for the retained floor

GitHub could not resolve the previous manifest pin `0b5858532fbef2ff3ce0be0b9e6e2c6d2cb8a28e`.
The floor manifest now pins published PR #12 commit
`47a337db74ca533639e23f06516ef0d87117428f`. Its tasks and configured generator
commands match the execution branch. Fresh G5 rebuilt all three tasks in a
clean detached worktree, byte-for-byte, in 266.358389039 seconds. No missing,
extra or changed files. Existing G0-G4 evidence and three-salt measurements
remain valid for the same artifact bytes. `G5-published.json` contains the
new check, and the old G5 record remains in the manifest as history.

The first recheck launcher failed before any gate with `FileExistsError`:
`safe_extract` needs an absent destination. A new `submission` child directory
fixed the launcher. This was not a generator or verifier failure.

Floor dqi SHA-256 `529b075009f7758abeda83a63407f0c1feeb51dd70631ae4335dfd28721b7e08`,
823297489 bytes. Floor ZIP SHA-256
`b6709a4692802091f169332630ef54f0c0d9ffe3a6bcd26179e278c2189975ba`, 91399451 bytes.

## Review boundary

All local commits stay on the assigned long PRA-193 execution branch. The branch
carries the existing integration tree through `3404dff`; no merge or branch
switch occurred during this continuation. PR #12 remains the generator review
target. PR #11 is the existing combined execution-branch PR and remains **do not
merge**; new experiment and corrected manifest evidence are on that branch.
John Wick must reconcile the evidence into the intended review/merge target.
PRA-203 and PRA-204 remain required before shipment; this result is engineering
evidence, not their verdict. The recorded provenance and shipping gates remain.
Rollback for this continuation is limited to the new experiment evidence and
manifest pointer/G5 record; generator code is unchanged. Keep DECISIONS rows.

## Verification of this continuation

`uv sync` (exit 0):

```text
Resolved 50 packages in 2ms
Checked 12 packages in 0.33ms
```

`uv run pytest` (exit 0):

```text
============================= test session starts ==============================
platform linux -- Python 3.13.13, pytest-9.1.1, pluggy-1.7.0
rootdir: /home/cld-main/work/.paperclip-worktrees/quantum-hackathon/op-vqcc/PRA-193-regarding-my-quantum-hackathon-project-you-should-know-that-the-highest-score-on-the-hackathon-project-t
configfile: pyproject.toml
testpaths: tests
collected 165 items / 1 skipped

tests/test_costs.py ...............                                      [  9%]
tests/test_dqi_algebra.py .                                              [  9%]
tests/test_dqi_formulas.py .                                             [ 10%]
tests/test_dqi_provenance.py ....                                        [ 12%]
tests/test_g0.py ...................                                     [ 24%]
tests/test_gate_contract.py ......                                       [ 27%]
tests/test_install_kickmix.py ........                                   [ 32%]
tests/test_invsqrt_parity.py ...                                         [ 34%]
tests/test_invsqrt_provenance.py ....                                    [ 36%]
tests/test_ledger_evidence.py ............                               [ 44%]
tests/test_ledger_gates.py .......................                       [ 58%]
tests/test_ledger_manifest.py ...............                            [ 67%]
tests/test_ledger_scorecard.py ..........                                [ 73%]
tests/test_pra177_generators.py ...                                      [ 75%]
tests/test_reference_identity.py .................                       [ 85%]
tests/test_review_boundaries.py ..                                       [ 86%]
tests/test_scoring.py .....                                              [ 89%]
tests/test_smoke.py ..                                                   [ 90%]
tests/test_status_page.py ...............                                [100%]

================== 165 passed, 1 skipped in 64.50s (0:01:04) ===================
```

No production behavior changed, so no new unit regression test was added.
The substantive checks are the baseline artifact identity, the full experimental
verifier and G4 rejection, plus the reachable-commit G5 rebuild. The full G3
comparison was a failing test of the compression hypothesis. Compact64 has
11 phase errors against the floor candidate's recorded 3; no new salt was tried.

The experimental G0-G4 loop took 311.978953959 seconds; G3 itself ran
approximately 197.7 seconds across all three tasks. Per-task timings and peak
memory were not instrumented in this continuation. The earlier baseline
0.85 GiB/worker observation was a sample, not a peak measurement.

The optional test skip is reported above. No live-stack, Kaggle, deployment,
merge or main-write checks were performed.
