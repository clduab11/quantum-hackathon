# PRA-293 dqi-only rollback

Restores **only `dqi.kmb`**: from the fused decoder (`7beea291…55f6`, candidate `pra293-fused`) back to the Schur
decoder (`1a1c60ae…8f48`, the `pra261-schur` bytes that submission-007 and submission-008 ship). invsqrt and all 26
chemistry members stay as they are. The result is archive-identical to submission-008.

## Command

```bash
bash ledger/evidence/pra293-fused/rollback/rehearsal-command.sh [OUTPUT_ROOT]   # OUTPUT_ROOT must not exist
```

What it does, and where it stops:

1. Refuses an existing `OUTPUT_ROOT` before any write.
2. Checks the pinned inputs: candidate zip `7a6489cd…eba0`, submission-008 zip `8e291840…8f21`, and the
   submission-008 and `pra280-rustad` / `pra261-schur` manifests read from `main` `33c8f82` with `git show`.
3. Requires the two archives to have the same 28 members and to differ in `dqi.kmb` only.
4. Extracts a `git archive` of `33c8f82` into `OUTPUT_ROOT/source`, runs `uv sync --frozen` and the Kickmix
   installer there, then regenerates the Schur dqi with `python -m tasks.dqi.generate_schur` (the dqi generator in
   `pra280-rustad`'s G5). No circuit is copied from an old zip. It fails unless the output is `1a1c60ae…8f48`.
5. Swaps that file into the extracted candidate bundle, repackages it with `ledger.archive.build_zip`, and fails
   unless all 27 other members are byte-equal to the candidate and the zip equals submission-008 byte for byte.

`check-target.sh ZIP` exits 0 only for the submission-008 archive.

## Rehearsal (2026-10-27)

| Item | Value |
|---|---|
| Output root | `/home/cld-main/work/vqcc-data/pra293-rollback-20261027` |
| Started / finished (UTC) | `16:18:10.159711434Z` / `16:23:47.486540666Z` |
| Exit status | **0** (`rehearsal-exit.json`) |
| Regenerated `dqi.kmb` | `1a1c60ae30f506ec5d05728d893f63d2e0c4952b0145af2081236bfef1e18f48` |
| Output `rollback.zip` | `8e2918400fd033440d350d4af76bc4bdfca3787cdf411dcbb974f03d3b4f8f21` = submission-008 |
| Members byte-equal to the candidate | 27 of 28 (all but `dqi.kmb`) |
| Source archives unchanged | yes (re-hashed at the end) |

Raw log: `rehearsal.log`. Every member hash before and after: `member-hashes.json`.

Negative controls (`negative-controls.log`): `check-target.sh` exits 1 on the candidate zip and 0 on the rollback
output; a repeat into the existing root is refused with exit 1 before any write.

## What this does not do

- `git revert` of the PRA-293 merge restores **source only**. It does not rebuild or replace any zip.
- **Nothing undoes a completed Kaggle submission.** If the fused bundle is uploaded, this procedure only gives a
  checked submission-008 archive for a later upload, which needs a slot and a ledger reservation.
