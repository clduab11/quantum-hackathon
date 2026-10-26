# PRA-261 formal Schur candidate

This evidence branch records the real gate run for the existing Schur bundle.
It adds no generator, verifier, gate-policy, or shipping-default changes.
The source implementation and `configs/gates/pra261-schur.yaml` are already
merged. Main at `6babc95e1ed3a61d399ac2a5e3643d023b635ae3` is the candidate's
clean generator commit. The existing upstream code is recorded truthfully as
`no-licence`; D-PRA273-01 defers licence checks and does not waive G5 rebuild.

Candidate: `ledger/manifests/candidates/pra261-schur.json`.
Parent: `pra250-hankel`, archive-identical to submission-006.
Zip: `/home/cld-main/work/vqcc-data/pra261-schur-port/pra261-schur.zip`.
SHA-256: `9fcb5fe2e82d052568e2c5857965cf87cb51ab0dd1f107ae00c188f8e07b11d5`.

See [commands.md](commands.md) for the environment and exact gate invocation.
All new gate records belong to this zip and the fixed public salt
`PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`. No seed or salt search occurred.

## Repository verification

```text
$ uv sync
Resolved 105 packages in 1ms
Installed 36 packages in 107ms
$ OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run pytest
================= 376 passed, 11 skipped in 177.50s (0:02:57) ==================
$ uv run python -m ledger.registers check
OK registers: 272 decisions, 6 notice files, legacy index unchanged
```

All three commands exited 0. Full test and register output are in
[pytest.log](pytest.log) and [registers.log](registers.log). Eleven skipped
cases were not verified by this run. This is an evidence-only change, so no
new behavioral test is added. The existing Schur complete-domain and oracle
tests ran in the suite; the original failure-first implementation evidence
remains in the PRA-261 history.

## Rollback and boundaries

The exact Schur-to-Hankel fallback was already rehearsed in PRA-278 at
`298ca0dbcad79349ad1cb559ba0fef0333e36a3d`. Its separate fallback archive is
`/home/cld-main/work/vqcc-data/pra278-schur-rollback-20261026/fallback.zip`,
SHA-256 `459b2f11778f5bbd576ce69b9f85156ca2c301bd2a3f74752adca5c2dadcbec7`.
That command returned exit 0 and preserved all ten non-DQI members byte-for-byte.
The unchanged packet is attached to PRA-261 as
`/api/attachments/b2741456-e761-4d17-b2ad-4caa6ce73f8e/content`.
The rehearsal was not repeated in this heartbeat.

Reverting this evidence branch has no runtime effect; retain its historical
records and leave the candidate unused. To restore the candidate's DQI,
use the pinned fallback command and evidence described in [commands.md](commands.md).
The shipped default remains Hankel. No upload, merge, production operation,
or public score is claimed. Candidate-specific review and John Wick's ledger
reservation/upload workflow remain separate from local gate clearance.

## Full-shot measurement

G3 and G4 passed on the exact zip, with no waivers.

| Task | Ratio | Q | Mean T | Shots |
|---|---:|---:|---:|---:|
| dfthcsos | 4.149479453986 | 833 | 20286.0 | 36608 |
| dqi | 47.593168768618 | 892 | 535327.7832421875 | 102400 |
| invsqrt | 13.164808636371 | 90 | 1437.5000155878406 | 200540928 |

Local geometric mean: **13.7504717063936**.
DQI max T: 535334; R: 1.2055843238398525; value/phase errors: 3/0;
epsilon upper bound: 0.000983909102617945. This exactly reproduces the
earlier point at the same fixed public salt. It beats the 26.30x floor,
but remains below John's 48.135x public 883-qubit comparison. No width
optimization is claimed. G3's content-addressed full evidence is
`ledger/evidence/pra261-schur/G3.json`, SHA-256
`11cd0ca2581200b7306e9b1d19142fc18641e6af05b1f898d0d6884964fd00f0`.

## Final gate result

```text
G0 PASS
G1 PASS
G2 PASS
G3 PASS
G4 PASS
G5 PASS
{"shipping_problems": [], "geometric_mean": 13.750471706393649, "elapsed_seconds": 897.634204514994}
```

Exit 0. [Raw gate log](gates.log), [rebuild detail](rebuild.json), and
[check receipts](checks.json). G5 regenerated all three tasks byte-for-byte:
zero missing, extra, or changed files; each generator exit 0. No circuit is
copied from a declared input. The only copied member is the approved
non-circuit chemistry factor `dfthcsos/submission.npz`, pinned to
`inputs/thc/femoco_thc_r5.npz` SHA-256
`809a992900937425f01a0593803921873f7bb472d590592c378d3ceb23657df5`.
The runner queued a hash-verified copy at `ledger/queue/pra261-schur.zip`
(ignored binary) and its tracked JSON pointer. Only the pointer and evidence
are committed. Local gate clearance is not candidate review or upload approval.
