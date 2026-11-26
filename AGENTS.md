# AGENTS.md — rules for every agent working in this repository

These rules bind every agent and session in this repo. If a task description disagrees with them, stop and ask
the board through The High Table before you go on.

## Branches and merges

- Work on `op-vqcc/<topic>` branches in `/home/cld-main/work/quantum-hackathon`.
- Never push `main`. Never force-push. Never merge your own PR; john-wick alone squash-merges, after his review (D-PRA304-01).
- Autonomy and who merges: see the `praxen-house-rules` skill. The only thing that needs Chris's approval is deleting a material file.
- Repo hosting: GitHub is the source of truth, mirrored to Entire (entire.com); agents push only to GitHub.
- Open a pull request for every branch and register it on the Paperclip ticket.
- Commit trailer: `Co-Authored-By: Paperclip <noreply@paperclip.ing>`.

## Merge queue (PRA-210)

john-wick squash-merges pull requests one after another and never resolves a conflict.

- One candidate, one pull request, cut from current `main`. No pull request bundles two tasks.
- Never cut a branch from another unmerged pull request. A squash merge drops that ancestry, so the stacked branch
  then conflicts with its own parent's changes.
- Before you hand a pull request to john-wick, run the merge-order gate over every open head and paste its
  report in the pull request body: `uv run python scripts/merge_gate.py` (add `--ref mine=HEAD` if your branch has
  no pull request yet). CI runs the same gate on every pull request and on every push to `main`.
- No pull request is reported to john-wick as ready unless the whole open queue passes the gate.
- If two open pull requests touch the same register entry, the second one rebases onto `main` after the first
  merges. The author resolves it, never john-wick.
- Registers are one file per entry, so ordinary work never shares a file:
  - a decision is a new file `docs/decisions/<id>.md` holding one table row; `docs/DECISIONS.md` is closed;
  - a third-party notice is a bullet in `notices/NN-<area>.txt` (one file per task area), not in `NOTICE`;
  - `ledger/manifests/index.csv` is derived from the manifests and is not committed.
- `uv run python -m ledger.registers check` must pass; `uv run pytest` runs it.

## Secrets

- Never read, print or copy secrets.
- The Kaggle API token belongs to john-wick only. It is read through Paperclip's secret API and is never written to
  disk, to logs, to commits or to issue comments.

## Machines

- Chris's Desktop copy (`C:\Users\cld-main\Desktop\github-projects\quantum-hackathon`) is not touched.
- All builds run in WSL.

## Verification

- No nonce or seed grinding. The verifier salts are secret, so grinding is wasted compute.
- Never ship an unverified task. If any task fails, the whole zip is rejected.

## Provenance and reuse (D-HERMES-20261126-01; R10 retired)

- R10's own-generator rule is retired by Chris's ruling of 2026-11-26 (D-HERMES-20261126-01). In his words: "Every
  circuit does NOT have to come from my own generator; I can use outside circuits provided I follow appropriate
  licensure. Additionally I can absorb the circuit into my repo as is, and utilize work I've done on top of that to
  potentially augment the circuit in question."
- Outside circuits may ship. Absorb one as a declared input of kind `vendored_circuit`, pinned by URL, version and
  SHA-256, with its upstream licence and author credit kept beside it (a bullet in `notices/NN-<area>.txt` and the
  licence and source in the ledger). Only licences that allow reuse and redistribution qualify (Apache-2.0,
  CC-BY-4.0, or another licence the-adjudicator accepts); keep each licence's notice and attribution terms.
- An absorbed circuit may ship as is (byte-identical to its pin) or augmented by our own committed code. An augmented
  circuit is generated deterministically from the pinned input, keeps the upstream licence and credit, and records
  what we changed. G0 to G5 still run on every upload; G5 still checks that every shipped file is the pinned input or
  is rebuilt byte for byte from committed code.
- The k256.dev dqi artifact and the jday96314 Schur origin repo stay banned: their licence chain is not established.
- Parents (Apache-2.0 notebooks, CC-BY-4.0 Zenodo code) are recorded in the ledger with URL and licence.
- The full licence and lineage review of every absorbed source, and the author credits, are completed before the
  2027-01-20 23:59 UTC final deadline (D-HERMES-20261113-01).

## Decisions and negative results

- The decisions register is append-only: the closed rows in `docs/DECISIONS.md` plus one file per new decision in
  `docs/decisions/<id>.md`. It is also the negative-results memory: failed hypotheses are recorded and never
  deleted. Correct an old row by adding a new decision file that supersedes it.

## Submissions

- Only john-wick submits to Kaggle. Hard cap: 3 submissions per UTC day, checked by the ledger **before** the upload.
- The upload runs only inside `uv run python -m ledger.scorecard submit`, or between `reserve` and `record`. No upload
  without a reservation; a failed or uncertain upload keeps its reservation until it is reconciled (PRA-211).
- Every submission is recorded in the ledger.

## Large files

- Large binaries (`.kmb`, competition data, zips) are never committed. Commit their SHA-256 in the ledger instead.

## Scope

- Majorana and hardware topics are out of scope.

## Tests

- `uv sync` and `uv run pytest` must pass before a branch is called ready.
