## Summary

Port SomeJoint submission-9 DQI to a new source-only Hankel/cyclic Gold path. The existing #33 decoder remains available. Retain the independently written mask projection and the audited arithmetic lineage.

The fixed-salt full verifier measures 26.295712807× against 2.4439e13, with Q883, mean T996048.1979785156, zero value errors and one phase error in 102400 shots. This clears the 25× floor; the matching public phase-error baseline is still requested on PRA-250. Do not treat this PR as accepted or ready to merge until that condition and the whole queue gate are resolved.

## Implementation notes

Source: SomeJoint kernel140675727 v7, UTF-8 SHA256 3b0df548f40676117fb6f53cd7c9ab0fc5ca29b7ed56f90581921e443e92d7eb. Explicit Apache-2.0 grant in cell34. Per-file pins, licence, notices, excluded inputs and inheritance are in tasks/dqi/hankel/PROVENANCE.md. No public circuit or notebook output is a generator input.

The phase stage needs an explicit norm-recycling inverse import to reproduce the upstream runtime substitution. Static T996829 matches all five public stage counts. The projection changes the byte hash, and the verifier derives seeds from that hash plus salt. No seed/salt search was used. The first draft and its measurement remain recorded.

A task-specific gate config combines this DQI with the current invsqrt and the already merged Gluzdov v8/J10 chemistry generator. It does not change default.yaml or import another unmerged branch.

## Verification

- `uv sync`: resolved96, checked36.
- `uv run pytest -q tests/test_dqi_hankel.py`: three failing tests before implementation; final five tests passed.
- `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run pytest -q`: 356passed,7skipped in256.57s. Optional GPU/notebook dependencies account for the skips.
- `uv run python -m ledger.registers check`: passes.
- Full fixed-salt verifier: PASS,102400shots,0value errors,1phase error.
- Exact-zip G0–G5: all PASS, no waivers, shipping_problems=[]. Local GM11.283239253337468. G5 rebuild from4305da8 matches every file. A G4 parent-id error was corrected; its failed receipt is retained. See docs/reports/pra250-dqi.md and ledger/evidence/pra250-hankel.
- `uv run python scripts/merge_gate.py --ref mine=HEAD`: could not run; GitHub open-PR enumeration returned HTTP403 rate-limit exceeded. Governed tool discovery separately returned gateway_token_revoked. No whole-queue PASS is claimed.

## Risk and rollback

This remains a sampled decoder with rare degree-gap exceptions. Finite tests do not prove universal correctness. Select the unchanged #33 generator/config to revert the candidate path; no main, production config, live service or upload was changed. Board merges; John Wick uploads only after the task requirements are resolved.
