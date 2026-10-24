# P0-4 verification results

Observed in WSL on 2026-10-24 UTC. Full reference calibration and a separate
full reference ZIP scoring run both passed. One fixed public local salt was used.

| Task | Q | Executed Toffolis | T (see units below) | Failures | epsilon_plus | Cost | Ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| invsqrt | 260 | 7735.0 | 1010.3728263889526 | 0 | None | 2076774.233715282 | 1.0 |
| dqi | 1893 | 5725108.861992188 | 5725108.861992188 | 0 | 0.0008660587301657926 | 24439465632206.816 | 1.0 |
| dfthcsos | 730 | 93237.0 | 93237.0 | 0 | None | 3355599588.3155365 | 1.0 |

```text
uv sync
Resolved 14 packages; checked 12 packages
uv run pytest -q
41 passed
uv run python ledger/gates/g0_preflight.py /home/cld-main/work/vqcc-data/reference.zip
G0 PASS: all metric files checked; no simulation performed.
uv run python harness/score_local.py /home/cld-main/work/vqcc-data/reference.zip
{"geometric_mean": 1.0, "scope": "fixed public local salt"}
```

All commands exited 0. Three constructed invalid ZIPs were also passed to the scorer:

```text
bad instruction: exit=1
REJECT: invsqrt.kmx is invalid: Failed to parse kmx line (unknown operation name): 'INVALID q0'
duplicate task: exit=1
REJECT: The submission must contain exactly one invsqrt.kmx or invsqrt.kmb, found 2.
oversized decoded NPZ: exit=1
REJECT: dfthcsos/submission.npz is invalid: the arrays in submission.npz take 124,824,616 bytes, above the limit of 67,108,864
```

The tests forbid Simulator construction during G0 and prove that malformed ZIPs
never reach baseline loading or verifier execution. Skill validation returned
`Skill is valid!`; all four CLI help commands succeeded.

Invsqrt T is synthesized total T gates; DQI and DFTHC T is a Toffoli resource.
`None` means epsilon_plus does not apply to that task. DQI executed mean differs
from its static 5,725,461 count, as expected from conditional execution.

## Evidence hashes

- `reference-baseline.jsonl`: `e9bb0d373064b845562ac68bc1be25fa2fffb69b07d7d78dd2321b2e2a490b37`
- `reference-score.jsonl`: `cd21d4c14f1d6261845fc917123d930a7944191e1dc0766863b894c77a713713`
- `reference-calibration.stderr.log`: `3f823812a87679db48d2518f49809c7c9c6147693a667ea0f6f91b8e8354d058`
- `reference-score.stderr.log`: `3f823812a87679db48d2518f49809c7c9c6147693a667ea0f6f91b8e8354d058`
- `pra174-pytest.log`: `2972e2d48c593979cda048564306c1717f86a90219cdcc7529f2bf8057853e73`

Full output and environment hashes are preserved in the Paperclip PRA-174
`verify-log` document and its attached verification log.

## Limit and review

The reference Lambda/E_gap formula is independently checked. The public lineage
source provides only lambda_eff=47.558542335159316 and Q/T constants, so its test
checks that reported scalar/cost, not an independently derived Lambda/E_gap pair.
The independent 47.56 derivation remains unresolved. See decision D-PRA174-07.

This is local public-salt evidence, not a Kaggle acceptance claim or provenance
approval. The Adjudicator reviews the tooling before use on main; the board merges.

## Review corrections (2026-10-24)

The regression checks first failed on the original implementation: duplicate
calibration task records raised no error, and the repository-venv boundary helper
did not exist. After correction:

```text
uv sync
Resolved 14 packages; Checked 12 packages
uv run pytest -q
74 passed in 1.07s
```

All five CLI `--help` commands exit 0. Tests now include changed reference bytes,
relocation of identical bytes, extra/missing reference files, changed baseline
identity, duplicate/missing task records, missing/failed PASS evidence, missing
full-shot evidence, changed salt and cost mismatches. They prove rejected
calibration input never reaches parsing or simulation.

A separate engineer-run check copied the three setup scripts into a new scratch
repository and created its own CPython 3.13.13 `.venv` with `uv venv`. It used the
real inventoried data directory and extension. Actual output, with the scratch
prefix shortened here (the attachment contains full commands and paths):

```text
install_kickmix.py DATA --dry-run -> Would create: SCRATCH/.venv/.../vqcc_local.pth; exit=0
install_kickmix.py DATA -> kickmix 0.1; Created: SCRATCH/.venv/.../vqcc_local.pth; exit=0
install_kickmix.py DATA -> Unchanged: SCRATCH/.venv/.../vqcc_local.pth; exit=0
uninstall_kickmix.py DATA --dry-run -> Would remove matching path file; exit=0
uninstall_kickmix.py DATA -> Removed matching path file; exit=0
uninstall_kickmix.py DATA -> Already absent; exit=0
install_kickmix.py DATA -> INSTALL REJECT: Existing path file conflicts; exit=1
uninstall_kickmix.py DATA -> ROLLBACK REJECT: Existing path file conflicts; exit=1
PASS: conflict bytes preserved; all writes were inside the scratch repository venv.
wrong interpreter -> INSTALL REJECT: Run with uv run in this repository venv (.venv, CPython 3.13); exit=1
```

The driver checked that reinstall preserves the file's stat information and that
both conflict refusals preserve its bytes. Unit tests also reject symbolic links,
dangling links, hard links, directories, linked parents and outside-venv targets.
This rollback removes only a matching path file; it does not undo `uv sync`.

The gate contract tests resolve the actual `module:function` hook paths. Valid G0
input reaches a G3 test consumer; invalid input stops before G3. Direct G3 calls
also reject malformed files before baseline loading or verification. A controlled
verifier fixture proves unchanged task summaries and the aggregate result.
The full scoring runs below use the real package verifiers.

The lineage test is still a reported-value regression. D-PRA174-07 is preserved;
D-PRA174-12 records the escalation for sourced inputs or a board scope amendment.
No acceptance or main-use approval is claimed here.

## Full verification after review corrections

Fresh calibration verified all inventoried reference hashes, then passed all three
full verifiers. A separate full ZIP scoring run used that new baseline and passed:

```text
uv run python harness/calibrate_reference.py
invsqrt PASS cost=2076774.233715282
dqi PASS cost=24439465632206.816
dfthcsos PASS cost=3355599588.3155365
complete=true; exit=0
uv run python harness/score_local.py /home/cld-main/work/vqcc-data/reference.zip
all ratios=1.0
{"geometric_mean": 1.0, "scope": "fixed public local salt"}
exit=0
```

The old baseline was preserved as `reference-baseline-before-review.jsonl`. The
validated new baseline was atomically copied to the default
`reference-baseline.jsonl`. Both full runs keep the original fixed public salt and
full shot counts. The values in the original results table still apply.

Review evidence hashes (all files are outside git):

- `pra174-tests-review.log`: `87bfeebc63f0d04d8bd6bc7d5de9bbdd89e3a4a79a2e2c845b4c9bbb83a3e5fe`
- `pra174-install-review.log`: `e48beba76bbe0c50bd2ca37ca9de4a0a6c1f69ac775e95558b822ce6e9f96568`
- `reference-baseline-review.jsonl`: `51d069cdfa0f2f41f9b569d26031ca8568555153c60fa12f1ad5ef4cfaa15385`
- `reference-calibration-review.stderr.log`: `3f823812a87679db48d2518f49809c7c9c6147693a667ea0f6f91b8e8354d058`
- `reference-score-review.jsonl`: `4e94f65da689ec45edeeac641ea75416381fc724ade0172d9dc71cac6ed28217`
- `reference-score-review.stderr.log`: `3f823812a87679db48d2518f49809c7c9c6147693a667ea0f6f91b8e8354d058`
