# PRA-294 chemistry-only rollback (shipping candidate)

Restores **only the `dfthcsos/` members**: from the C59 J=4 chemistry (19 circuits plus factor `8229861b…fa87`,
candidate `pra294-c59`, zip `f569b107…7435`) back to the rustad J=3 chemistry (25 circuits plus factor
`27dda66f…adad`) that `pra293-fused-invsqrt` (#65) ships. `invsqrt.kmb` (`17fc223d…41ad`) and `dqi.kmb`
(`7beea291…55f6`) stay as they are. The result is archive-identical to `pra293-fused-invsqrt` (zip `22258bb5…f27d`).
#65's own dqi-only rollback (`ledger/evidence/pra293-fused-invsqrt/rollback/`) continues from there.

## Command

```bash
bash ledger/evidence/pra294-c59/rollback/rehearsal-command.sh [OUTPUT_ROOT]   # OUTPUT_ROOT must not exist
```

What it does, and where it stops:

1. Refuses an existing `OUTPUT_ROOT` before any write.
2. Checks the pinned inputs: candidate zip `f569b107…7435` and `pra293-fused-invsqrt` zip `22258bb5…f27d`. It reads
   the `pra293-fused-invsqrt` manifest from `main` `4b757e8` with `git show` and requires its chemistry to be the
   rustad factor.
3. Requires the two archives to agree on every member outside `dfthcsos/` and the candidate factor to be C59.
4. Extracts a `git archive` of `4b757e8` into `OUTPUT_ROOT/source`. It runs `uv sync --frozen` and the Kickmix
   installer there, then regenerates rustad chemistry with `python -m tasks.dfthcsos.rustad` (the chemistry generator
   in `pra293-fused-invsqrt`'s G5). No circuit is copied from an old zip. It fails unless all 26 outputs match the
   `pra293-fused-invsqrt` pins.
5. Replaces `dfthcsos/` in the extracted candidate bundle and repackages it with `ledger.archive.build_zip`. It fails
   unless `invsqrt.kmb` and `dqi.kmb` are byte-equal to the candidate and the zip equals `pra293-fused-invsqrt` byte
   for byte.

`check-target.sh ZIP` exits 0 only for the `pra293-fused-invsqrt` archive.

## Rehearsal (2026-10-27)

| Item | Value |
|---|---|
| Output root | `/home/cld-main/work/vqcc-data/pra294-c59-rollback-20261027` |
| Started / finished (UTC) | `20:41:35.329636494Z` / `20:42:18.039907065Z` |
| Exit status | **0** (`rehearsal-exit.json`) |
| Delta | 20 members restored (`angle_k_0..18.kmb`, `submission.npz`), 6 added (`angle_k_19..24.kmb`), 0 removed |
| Output `rollback.zip` | `22258bb57f1a711336567cb8771c7f88936d903af7727ab0bbd993fb72e5f27d` = `pra293-fused-invsqrt` |
| Members byte-equal to the candidate | `dqi.kmb`, `invsqrt.kmb` (everything outside `dfthcsos/`) |
| Source archives unchanged | yes (re-hashed at the end) |

Raw log: `rehearsal.log`. Every member hash before and after: `member-hashes.json`.

Negative controls (`negative-controls.log`): `check-target.sh` exits 1 on the candidate zip and 0 on the rollback
output. A repeat into the existing root is refused with exit 1 before any write.

## What this does not do

- `git revert` of the PRA-294 merge restores **source only**. It does not rebuild or replace any zip.
- **Nothing undoes a completed Kaggle submission.** If this bundle is uploaded, the procedure only gives a checked
  `pra293-fused-invsqrt` archive for a later upload. That upload needs a slot and a ledger reservation.
