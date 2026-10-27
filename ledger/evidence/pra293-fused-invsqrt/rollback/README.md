# PRA-293 dqi-only rollback (shipping candidate)

Restores **only `dqi.kmb`**: from the fused decoder (`7beea291…55f6`, candidate `pra293-fused-invsqrt`) back to the
Schur decoder (`1a1c60ae…8f48`, the `pra261-schur` bytes that submission-007, submission-008 and #62's
`pra281-invsqrt-port` ship). The port invsqrt (`17fc223d…41ad`) and all 26 chemistry members stay as they are. The
result is archive-identical to `pra281-invsqrt-port` (#62, zip `5c8db085…cecd`).

`pra281-invsqrt-port` is submission-008 with only `invsqrt.kmb` changed (checked by this script). Its own
invsqrt-only rollback, `ledger/evidence/pra281-invsqrt-port/rollback.py` (#62), continues from there to
submission-008 (`8e291840…8f21`).

## Command

```bash
bash ledger/evidence/pra293-fused-invsqrt/rollback/rehearsal-command.sh [OUTPUT_ROOT]   # OUTPUT_ROOT must not exist
```

What it does, and where it stops:

1. Refuses an existing `OUTPUT_ROOT` before any write.
2. Checks the pinned inputs: candidate zip `22258bb5…f27d` and `pra281-invsqrt-port` zip `5c8db085…cecd`. It reads the
   `pra281-invsqrt-port`, `pra261-schur` and submission-008 manifests from `main` `c72649c` with `git show`. It
   requires `pra281-invsqrt-port` to carry the Schur dqi and the port invsqrt, and to differ from submission-008 in
   `invsqrt.kmb` only.
3. Requires the two archives to have the same 28 members and to differ in `dqi.kmb` only.
4. Extracts a `git archive` of `c72649c` into `OUTPUT_ROOT/source`. It runs `uv sync --frozen` and the Kickmix
   installer there, then regenerates the Schur dqi with `python -m tasks.dqi.generate_schur` (the dqi generator in
   `pra281-invsqrt-port`'s G5). No circuit is copied from an old zip. It fails unless the output is `1a1c60ae…8f48`.
5. Swaps that file into the extracted candidate bundle and repackages it with `ledger.archive.build_zip`. It fails
   unless all 27 other members are byte-equal to the candidate and the zip equals `pra281-invsqrt-port` byte for byte.

`check-target.sh ZIP` exits 0 only for the `pra281-invsqrt-port` archive.

## Rehearsal (2026-10-27)

| Item | Value |
|---|---|
| Output root | `/home/cld-main/work/vqcc-data/pra293-fused-invsqrt-rollback-20261027` |
| Started / finished (UTC) | `17:39:30.958680568Z` / `17:43:44.728251640Z` |
| Exit status | **0** (`rehearsal-exit.json`) |
| Regenerated `dqi.kmb` | `1a1c60ae30f506ec5d05728d893f63d2e0c4952b0145af2081236bfef1e18f48` |
| Output `rollback.zip` | `5c8db085d18872b17dc16890a2afd6ea8b3c63d3dc513b853ba0ac20b797cecd` = `pra281-invsqrt-port` |
| Members byte-equal to the candidate | 27 of 28 (all but `dqi.kmb`) |
| Source archives unchanged | yes (re-hashed at the end) |

Raw log: `rehearsal.log`. Every member hash before and after: `member-hashes.json`.

Negative controls (`negative-controls.log`): `check-target.sh` exits 1 on the candidate zip and 0 on the rollback
output. A repeat into the existing root is refused with exit 1 before any write.

## What this does not do

- `git revert` of the PRA-293 merge restores **source only**. It does not rebuild or replace any zip.
- **Nothing undoes a completed Kaggle submission.** If this bundle is uploaded, the procedure only gives a checked
  `pra281-invsqrt-port` archive, or submission-008 after #62's step, for a later upload. That upload needs a slot and
  a ledger reservation.
