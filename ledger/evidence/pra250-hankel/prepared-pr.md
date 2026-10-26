## Summary

Port SomeJoint submission-9 DQI to a new source-only Hankel/cyclic Gold path. The existing #33 decoder remains available. Retain the independently written mask projection and the audited arithmetic lineage.

The fixed-salt full verifier measures 26.295712807× against 2.4439e13, with Q883, mean T996048.1979785156, zero value errors and one phase error in 102400 shots. This clears the 25× floor; John Wick accepts the phase condition under D-PRA202-23. This is task-owner acceptance, not a same-sample statistical comparison. The whole-queue gate must pass before merge readiness.

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
- Exact-zip G0–G5: all PASS, no waivers, shipping_problems=[]. Local GM11.283239253337468. G5 first rebuilt local commit 4305da8; an appended G5 receipt also rebuilds published source commit 8e53362324fef5816baf58e699fa002a08596d7a byte-for-byte. Original identity and receipts are retained. A G4 parent-id error was corrected; its failed receipt is retained. See docs/reports/pra250-dqi.md and ledger/evidence/pra250-hankel.
- Governed publication is restored. Published source tree a3a31943a218b7447b66bc44d0efb29793a5dc42 equals the local source/evidence tree.
- Whole open queue: `uv run python scripts/merge_gate.py --pr 43 --pr 44 --pr 45 --pr 46 --ref mine=HEAD` completed: FAIL, 120 permutations, 0 clean. Existing PR #43 conflicts with main in notices/30-dfthcsos.txt, pyproject.toml and uv.lock. Queue repair belongs to PRA-260. This PR stays draft pending queue repair. PR #47 appeared after that snapshot; the six-head report in the PR body supersedes this initial snapshot.

## Risk and rollback

This remains a sampled decoder with rare degree-gap exceptions. Finite tests do not prove universal correctness. For a DQI-only local fallback, use the [pinned command and rehearsal in PRA-275](../pra275-rollback/rollback.md). Do not select the whole #33 gate config: it would also replace chemistry. The checked procedure regenerates only DQI and preserves current chemistry/invsqrt bytes and all historical records. A local rollback cannot undo the completed Kaggle upload. Any later upload belongs to John Wick under the ledger reservation and three-per-UTC-day cap. Board merges; candidate sign-off remains a separate review.
