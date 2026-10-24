---
name: kickmix-verify
description: Preflight and score a VQCC submission ZIP locally with the supplied kickmix verifiers; interpret costs and failures.
---

Use the repository's documented CPython 3.13 environment and installed competition
package. See `docs/handoffs/p0-4-kickmix-build.md` for setup and reference calibration.
Use the same metric snapshot, verifier imports, full shots and fixed public local
salt as the baseline. Do not search seeds, change shots, or use private salts.

1. Run `python ledger/gates/g0_preflight.py /path/to/submission.zip` in that
   environment. Exit 1 means reject; fix the stated file problem before simulation.
   G0 PASS proves file checks only, not circuit correctness or provenance.
2. Run `python harness/score_local.py /path/to/submission.zip --baseline /path/to/reference-baseline.jsonl`.
   With uv, prefix either command with `uv run`. Capture stdout and stderr plus
   the exit code. A complete successful run prints all three tasks and `geometric_mean`.
3. Read Q, executed Toffolis, T and its unit, failures, epsilon_plus, cost and ratio.
   Invsqrt T includes rotation synthesis; DQI/DFTHC T is a Toffoli resource.
   epsilon_plus is applicable only to DQI. Any rejection invalidates the whole ZIP.
4. Record the ZIP SHA-256, module/baseline identities and full output in the ledger.
   Local scores use a public salt and do not establish Kaggle acceptance. Submission
   remains a separate authorized action; this skill never submits or installs itself.
