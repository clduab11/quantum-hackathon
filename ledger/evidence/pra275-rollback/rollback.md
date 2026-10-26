# PRA-275: submission-006 local DQI rollback

This procedure builds a **local fallback bundle**. It replaces only `dqi.kmb`
with the source-generated J-fraction circuit from PR #33, previously approved
and used in submission-005 (23.56×). It keeps the ten other submission-006
members byte-equal. It does not change a default generator or gate config.

A local rollback cannot undo the completed Kaggle upload. Any later upload is
john-wick's responsibility, with a ledger reservation before upload and the
maximum of three submissions per UTC day. This rehearsal grants no upload,
merge, candidate sign-off, or G0–G5 waiver.

Do not run `git revert 40bbad1`: decision records are append-only. This procedure
does not remove or edit decision, provenance, candidate, or submission records.
The historical `prepared-pr.md` wording is superseded by this checked procedure.
Do not select `configs/gates/pra236-jfraction.yaml`: it also changes chemistry.

## Exact command and boundary

Run the following block in WSL. Source is pinned to current main at preparation:
`3432001ec2d8eb0ed077e9f7dbab2e1586d89cc7`. The J-fraction generator is unchanged
since PR #33 (`8af2a0d`). This command uses a clean archive of that commit,
its frozen lockfile, and the hash-checked local Kickmix package. No circuit is
passed to the DQI generator. The original submission zip is read only as a
container of the ten members that must be retained.

Working directory is the PRA-275 execution worktree below. All output is under
`/home/cld-main/work/vqcc-data/pra275-rollback-20261026`: a source snapshot,
its local venv/path file, regenerated `generated/dqi.kmb`, extracted `bundle/`,
`fallback.zip`, and `member-hashes.json`. Only `bundle/dqi.kmb` is overwritten,
after generation and hash validation. The original queue zip stays untouched.
`uv` also uses its normal local dependency cache. No global installation occurs.

The output root must not exist. A second invocation refuses to overwrite it.
For a separate rehearsal, select another unused local output root and record it.
Neither the fallback nor any binaries belong in Git.

```bash
set -euo pipefail
cd /home/cld-main/work/.paperclip-worktrees/quantum-hackathon/op-vqcc/hankel-rollback-evidence
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --frozen python - <<'PY'
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile

pin = '3432001ec2d8eb0ed077e9f7dbab2e1586d89cc7'
root = Path('/home/cld-main/work/vqcc-data/pra275-rollback-20261026')
original = Path('/home/cld-main/work/vqcc-data/queue/pra250-hankel.zip')
package = Path('/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation')
original_hash = '459b2f11778f5bbd576ce69b9f85156ca2c301bd2a3f74752adca5c2dadcbec7'
old_dqi = 'dec77920d4b9f5964b6cd52c947aa0c91468d56b7ed28cd475fdfc18d067729d'

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def run(args, cwd):
    print('COMMAND', ' '.join(map(str, args)), flush=True)
    result = subprocess.run(list(map(str, args)), cwd=cwd, check=False)
    print('EXIT', result.returncode, flush=True)
    result.check_returncode()

require(digest(original) == original_hash, 'Wrong source zip; no rollback performed')
require(not root.exists(), 'Output root already exists; preserve prior rehearsal')
require(subprocess.check_output(['git', 'rev-parse', pin], text=True).strip() == pin,
        'Pinned source commit is unavailable')
root.mkdir()
source = root / 'source'
source.mkdir()
with (root / 'source.tar').open('wb') as stream:
    subprocess.run(['git', 'archive', pin], stdout=stream, check=True)
with tarfile.open(root / 'source.tar') as archive:
    archive.extractall(source, filter='data')
print('PIN', pin, 'WORKING', Path.cwd(), 'OUTPUT', root, flush=True)
run(['uv', 'sync', '--frozen'], source)
run(['uv', 'run', '--frozen', 'python', 'scripts/install_kickmix.py', package], source)
manifest = json.loads((source / 'ledger/manifests/candidates/pra250-hankel.json').read_text())
require(manifest['zip_sha256'] == original_hash, 'Source manifest mismatch')
expected = {name: sha for task in manifest['tasks'].values()
            for name, sha in task['files'].items()}
sys.path.insert(0, str(source))
from ledger.archive import safe_extract, build_zip
bundle = safe_extract(original, root / 'bundle')

def hashes(directory):
    return {p.relative_to(directory).as_posix(): digest(p)
            for p in sorted(directory.rglob('*')) if p.is_file()}

before = hashes(bundle)
require(before == expected, 'Source member mismatch')
require(before['dqi.kmb'] != old_dqi, 'Expected Hankel source, not a prior rollback')
print('BEFORE: rollback target not met; dqi =', before['dqi.kmb'], flush=True)
generated = root / 'generated'
run(['uv', 'run', '--frozen', 'python', 'tasks/dqi/generate_jfraction.py',
     '--out', generated], source)
require(hashes(generated) == {'dqi.kmb': old_dqi}, 'Generated DQI hash/file-set mismatch')
shutil.copyfile(generated / 'dqi.kmb', bundle / 'dqi.kmb')
after = hashes(bundle)
target = {**before, 'dqi.kmb': old_dqi}
require(after == target, 'Rollback changed a non-DQI member')
fallback = build_zip(bundle, root / 'fallback.zip')
with zipfile.ZipFile(fallback) as archive:
    require(len(archive.namelist()) == len(target), 'Unexpected zip member count')
    archived = {}
    for name in archive.namelist():
        with archive.open(name) as stream:
            archived[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
require(archived == target, 'Fallback zip member mismatch')
require(digest(original) == original_hash, 'Original zip changed')
receipt = dict(source_commit=pin, source_zip=str(original), source_zip_sha256=original_hash,
               output_zip=str(fallback), output_zip_sha256=digest(fallback),
               before=before, after=after,
               changed_members=[name for name in before if before[name] != after[name]],
               unchanged_members=10, original_zip_unchanged=True)
(root / 'member-hashes.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2), flush=True)
print('PASS: only dqi.kmb changed; ten other members and original zip unchanged', flush=True)
PY
```

## Expected member hashes

The input zip is SHA-256
`459b2f11778f5bbd576ce69b9f85156ca2c301bd2a3f74752adca5c2dadcbec7`.
The expected output has exactly these eleven members:

| Member | SHA-256 after rollback |
|---|---|
| dqi.kmb | `dec77920d4b9f5964b6cd52c947aa0c91468d56b7ed28cd475fdfc18d067729d` |
| invsqrt.kmb | `75e8a0e2341bb3e8f8ded1ec1d53e24437410c69e887da9daf7d49bfcc28c2dd` |
| dfthcsos/angle_k_0.kmb | `60d9dfb7a5ec6d172232f4d7081b858ce6868eea0ca2ee99ed3c99a195c3d0bb` |
| dfthcsos/angle_k_1.kmb | `4079e0a08491fc3e42df613b09fd6c8399364bdf8cc508c0de2814f7ddf75c19` |
| dfthcsos/angle_k_2.kmb | `cacdff488e6ea968f9f60f80072ca9285036b65a98a1cd60576190960458eb1a` |
| dfthcsos/angle_k_3.kmb | `dbe4415e56782c83b6a53045ca7325a66528ae3812a28e577e0a527d89ba77bd` |
| dfthcsos/angle_k_4.kmb | `6e0dcbe0f75a631c60e5d3affcf01179c4599abea05c053ef94d04e0a5f7d472` |
| dfthcsos/angle_k_5.kmb | `58b75e436ff504af19b40fdb23337c7c548db8f84a3bdc9710d8f8303deee41f` |
| dfthcsos/angle_k_6.kmb | `9df59056b173c4205a944c59edb4cfe5c77f0fd6003dbb34f2864910204b8d09` |
| dfthcsos/angle_k_7.kmb | `86bc88ad3aad4553f60f3eac26807acd42a949ebc48bbb2443688193f9a9b1f4` |
| dfthcsos/submission.npz | `809a992900937425f01a0593803921873f7bb472d590592c378d3ceb23657df5` |

## Verification boundary

This is an artifact rollback rehearsal, not a fresh scoring or shipping run.
It regenerates DQI and checks the exact zip and all member hashes. It reuses the
already verified chemistry and invsqrt bytes without claiming to regenerate
them in this rehearsal. The prior G0–G5 records remain intact; this procedure
does not issue a new gate receipt or measure the public score.

## Rehearsal result (2026-10-26)

The verbatim command above ran from this worktree, based on current remote main
`3432001ec2d8eb0ed077e9f7dbab2e1586d89cc7`, from 18:37:53 to 18:40:19 UTC.
Exit status: **0**. Every subprocess exited 0. Regeneration produced
`dec77920d4b9f5964b6cd52c947aa0c91468d56b7ed28cd475fdfc18d067729d`.
Only `dqi.kmb` changed. The original zip hash remained unchanged.

Fallback zip SHA-256: `66de2d131cc2c314e9683799866d8e76e6b2b434a8e9061c401037f1dbea28a8`.
This is a local artifact, not a new submission record or upload authorization.

- [Verbatim command](rehearsal-command.txt), [raw output](rehearsal.log),
  [exit status and timestamps](rehearsal-exit.json), [member hashes](member-hashes.json).
- [Direct byte comparison](byte-comparison.md): all ten retained members equal;
  command exit 0.
- [Negative controls](negative-checks.md): the old config fails the current
  chemistry contract, and the original zip fails the required fallback DQI hash;
  each exits 1 as expected. The latter target passes after the rollback.
- [Repeat refusal](repeat-refusal.log): exact same command exits 1 before writes
  because the output directory already exists; previous evidence is preserved.
- `uv sync`: exit 0, resolved 96 packages, installed 36 ([log](uv-sync.log)).
- `uv run python scripts/install_kickmix.py
  /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation`:
  exit 0; project-local setup only ([log](kickmix-setup.log)).
- `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run pytest`: exit 0,
  **365 passed, 8 skipped in 126.06s** ([complete output](pytest.log)).
- `uv run python -m ledger.registers check`: exit 0,
  `OK registers: 258 decisions, 6 notice files, legacy index unchanged`
  ([log](registers.log)).
- `git diff --check`: exit 0.

The entire open queue is **not ready**. Automatic PR discovery in
`uv run python scripts/merge_gate.py --ref mine=HEAD` exited 2 due to GitHub's
anonymous API rate limit ([log](merge-gate.log)). The GitHub connector returned
all open heads (#43, #50, #51). Running the same gate with that explicit list,
`uv run python scripts/merge_gate.py --pr 43 --pr 50 --pr 51 --ref mine=HEAD`,
exited 1: **24 permutations, 0 clean** ([report](merge-gate-explicit.log)).
PR #43 conflicts even directly against main in `notices/30-dfthcsos.txt`,
`pyproject.toml`, and `uv.lock`. Those files are outside this evidence-only diff
and were left alone. The report identifies the exact source commit it tested;
refresh it after queue repair and before publication/readiness.

## Review and continuation

PR publication waits for Chris's explicit selection on PRA-233's card
`a0793a7a-0a61-4f6c-83cc-137b494ddcc3`; the card was pending during this rehearsal.
The PRA-270 Adjudicator re-review and PRA-271 watchdog hold are separate gates.
No PR, merge, revert, service change, host change, or upload was performed.

Schur follow-through belongs on PRA-261 / PR #50: before its formal G0–G5,
record a pinned **Schur-to-Hankel** DQI-only fallback and rehearse it on the
exact Schur bundle, preserving that bundle's other members. This Hankel-to-
J-fraction receipt does not prove a Schur rollback. PRA-261 remains dependent
on PRA-272/PRA-273; its G0–G5 takes precedence over this ticket's PR step once
that dependency lands. No Schur code or evidence was changed on this branch.
