## Summary

Replace submission-006's vague rollback advice with an exact, pinned WSL command and successful rehearsal. It regenerates PR #33 J-fraction DQI to `dec77920d4b9f5964b6cd52c947aa0c91468d56b7ed28cd475fdfc18d067729d` and replaces only that member in a local fallback zip. All ten chemistry/invsqrt members are unchanged by hashes and direct byte comparison.

## Implementation notes

Documentation and evidence only for PRA-275 / PRA-270. Source pin `3432001ec2d8eb0ed077e9f7dbab2e1586d89cc7`; command uses existing generator and archive helpers. No gate config or production code changed. Decision, provenance and submission records are preserved. Full command, paths, affected files, member hashes, logs and exit statuses are in `ledger/evidence/pra275-rollback/rollback.md`.

## Verification

- Verbatim documented rollback command: exit 0. Only DQI changed; all ten retained members byte-equal. Second invocation refuses overwrite with exit 1.
- Negative controls: old config fails chemistry-preservation contract; original source zip fails the fallback DQI target. Both fail with exit 1 as expected.
- `uv sync`: exit 0, resolved 96 packages, installed 36.
- `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run pytest`: exit 0, **365 passed, 8 skipped in 126.06s**.
- `uv run python -m ledger.registers check`: exit 0, `OK registers: 258 decisions, 6 notice files, legacy index unchanged`.
- `git diff --check`: exit 0.
- No new full verifier, G0–G5, Kaggle score or upload is claimed. Prior candidate receipts remain unchanged.

## Risk and rollback

A local rollback cannot undo the completed Kaggle upload. A later upload belongs to John Wick under the ledger reservation and three-per-UTC-day cap. No blanket revert of `40bbad1`: decision records are append-only. The local command checks the source zip before work, validates regenerated DQI before replacement, preserves the original zip and refuses an existing output root. Rehearsal artifacts remain outside Git.

## Publication hold and queue evidence

Prepared locally; **not opened**. Chris's PRA-233 card `a0793a7a-0a61-4f6c-83cc-137b494ddcc3` is pending. Adjudicator re-review is required. The Schur gate work takes priority when PRA-273 lands. Refresh the full queue report before publication or any readiness claim.

Automatic `uv run python scripts/merge_gate.py --ref mine=HEAD` exited 2 (GitHub API rate limit). The GitHub connector listed the complete open queue #43/#50/#51. `uv run python scripts/merge_gate.py --pr 43 --pr 50 --pr 51 --ref mine=HEAD` exited 1. Existing PR #43 conflicts with main; queue repair is outside this diff.

### Merge-order gate: FAIL

- repository `clduab11/quantum-hackathon`, base `main` at `3432001ec2d8eb0ed077e9f7dbab2e1586d89cc7`
- heads (4): #43 `331bb7dc3424`, #50 `f5d9effc7d1e`, #51 `b7ceb4f601ce`, mine `b533c475df45`
- excluded: none
- heads already in the base (they prove nothing): none
- orders squashed: 24 (every permutation); clean 0, conflicting 24

| squashed first | then conflicts | files |
| --- | --- | --- |
| (main) | #43 | `notices/30-dfthcsos.txt`, `pyproject.toml`, `uv.lock` |
| #50 | #43 | `notices/30-dfthcsos.txt`, `pyproject.toml`, `uv.lock` |
| #51 | #43 | `notices/30-dfthcsos.txt`, `pyproject.toml`, `uv.lock` |
| mine | #43 | `notices/30-dfthcsos.txt`, `pyproject.toml`, `uv.lock` |
| #50 → #51 | #43 | `notices/30-dfthcsos.txt`, `pyproject.toml`, `uv.lock` |
| #50 → mine | #43 | `notices/30-dfthcsos.txt`, `pyproject.toml`, `uv.lock` |
| #51 → #50 | #43 | `notices/30-dfthcsos.txt`, `pyproject.toml`, `uv.lock` |
| #51 → mine | #43 | `notices/30-dfthcsos.txt`, `pyproject.toml`, `uv.lock` |
| mine → #50 | #43 | `notices/30-dfthcsos.txt`, `pyproject.toml`, `uv.lock` |
| mine → #51 | #43 | `notices/30-dfthcsos.txt`, `pyproject.toml`, `uv.lock` |
| #50 → #51 → mine | #43 | `notices/30-dfthcsos.txt`, `pyproject.toml`, `uv.lock` |
| #50 → mine → #51 | #43 | `notices/30-dfthcsos.txt`, `pyproject.toml`, `uv.lock` |
| #51 → #50 → mine | #43 | `notices/30-dfthcsos.txt`, `pyproject.toml`, `uv.lock` |
| #51 → mine → #50 | #43 | `notices/30-dfthcsos.txt`, `pyproject.toml`, `uv.lock` |
| mine → #50 → #51 | #43 | `notices/30-dfthcsos.txt`, `pyproject.toml`, `uv.lock` |
| mine → #51 → #50 | #43 | `notices/30-dfthcsos.txt`, `pyproject.toml`, `uv.lock` |

