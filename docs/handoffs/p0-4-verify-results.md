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
