#!/usr/bin/env bash
# PRA-294 chemistry-only rollback: pra294-c59 -> pra293-fused-invsqrt (#65), i.e. the 20 C59 dfthcsos/
# members back to the 26 rustad members, with invsqrt.kmb and dqi.kmb kept.
# Rustad chemistry is regenerated from a git archive of main 4b757e8 (tasks.dfthcsos.rustad, the
# chemistry generator in pra293-fused-invsqrt's G5); no circuit is copied from an old zip.
# Usage: bash rehearsal-command.sh [OUTPUT_ROOT]   (OUTPUT_ROOT must not exist)
set -euo pipefail
ROOT="${1:-/home/cld-main/work/vqcc-data/pra294-c59-rollback-20261027}"
REPO=/home/cld-main/work/quantum-hackathon
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 - "$ROOT" "$REPO" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import zipfile

pin = '4b757e8d036cf5901d8d39b13d191bf8d8693657'
root, repo = Path(sys.argv[1]), Path(sys.argv[2])
data = Path('/home/cld-main/work/vqcc-data')
candidate = data / 'pra294-c59' / 'pra294-c59.zip'
parent = data / 'pra293-fused-invsqrt' / 'pra293-fused-invsqrt.zip'
package = data / 'google-verifiable-quantum-circuit-compilation'
candidate_hash = 'f569b107f4136d388636bcdb03f323b5c7483df463a3f8b6d682624de97e7435'
parent_hash = '22258bb57f1a711336567cb8771c7f88936d903af7727ab0bbd993fb72e5f27d'
rustad_npz = '27dda66f38c60821665cfc74e51d1bd2bfd2a7f0d902dbaffcdc5b26543dadad'
c59_npz = '8229861b3ee22316e144c900737dfc54f7a30ea88de77ff5391f3375d050fa87'

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def git(*args):
    return subprocess.check_output(['git', '-C', str(repo), *args])

def run(args, cwd):
    print('COMMAND', ' '.join(map(str, args)), flush=True)
    result = subprocess.run(list(map(str, args)), cwd=cwd, check=False)
    print('EXIT', result.returncode, flush=True)
    result.check_returncode()

def members(record):
    return {name: sha for task in record['tasks'].values() for name, sha in task['files'].items()}

def hashes(directory):
    return {p.relative_to(directory).as_posix(): digest(p)
            for p in sorted(directory.rglob('*')) if p.is_file()}

def inventory(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), 'Duplicate archive member')
        result = {}
        for name in sorted(names):
            with archive.open(name) as stream:
                result[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
        return result

started = datetime.now(timezone.utc).isoformat()
require(not root.exists(), 'Output root already exists; preserve prior rehearsal')
require(git('rev-parse', pin).decode().strip() == pin, 'Pinned source commit is unavailable')
require(digest(candidate) == candidate_hash, 'Wrong pra294-c59 archive; no rollback performed')
require(digest(parent) == parent_hash, 'Wrong pra293-fused-invsqrt archive')
target_manifest = json.loads(git('show', f'{pin}:ledger/manifests/candidates/pra293-fused-invsqrt.json'))
require(target_manifest['zip_sha256'] == parent_hash, 'pra293-fused-invsqrt manifest pin')
target = members(target_manifest)
require(target['dfthcsos/submission.npz'] == rustad_npz, 'pra293-fused-invsqrt chemistry is not rustad')
before = inventory(candidate)
require(inventory(parent) == target, 'pra293-fused-invsqrt member mismatch')
require(before['dfthcsos/submission.npz'] == c59_npz, 'candidate chemistry is not C59')
outside = sorted(n for n in set(before) | set(target) if not n.startswith('dfthcsos/'))
require(all(before.get(n) == target.get(n) for n in outside), 'Non-chemistry members differ; not a chemistry-only rollback')
delta = dict(restored_in_rollback=sorted(n for n in target if n in before and before[n] != target[n]),
             added_in_rollback=sorted(n for n in target if n not in before),
             removed_in_rollback=sorted(n for n in before if n not in target),
             unchanged=sorted(n for n in target if before.get(n) == target[n]))
require(all(n.startswith('dfthcsos/') for k in ('restored_in_rollback', 'added_in_rollback', 'removed_in_rollback')
            for n in delta[k]), 'Delta outside dfthcsos/')
require(delta['unchanged'] == outside, f"Unexpected unchanged set {delta['unchanged']}")
print('INPUTS VERIFIED', json.dumps({'pra294-c59': candidate_hash, 'pra293-fused-invsqrt': parent_hash, 'pin': pin}), flush=True)
print('DELTA', json.dumps({k: len(v) for k, v in delta.items()}), flush=True)

root.mkdir(parents=True)
source = root / 'source'
source.mkdir()
with (root / 'source.tar').open('wb') as stream:
    subprocess.run(['git', '-C', str(repo), 'archive', pin], stdout=stream, check=True)
with tarfile.open(root / 'source.tar') as archive:
    archive.extractall(source, filter='data')
run(['uv', 'sync', '--frozen'], source)
run(['uv', 'run', '--frozen', 'python', 'scripts/install_kickmix.py', package], source)
generated = root / 'generated'
run(['uv', 'run', '--frozen', 'python', '-m', 'tasks.dfthcsos.rustad', '--data', data, '--out', generated], source)
expected = {n: h for n, h in target.items() if n.startswith('dfthcsos/')}
require(hashes(generated) == expected, 'Regenerated chemistry differs from the pra293-fused-invsqrt pins')
print('REGENERATED dfthcsos/ matches pra293-fused-invsqrt:', len(expected), 'members', flush=True)

sys.path.insert(0, str(source))
from ledger.archive import safe_extract, build_zip
bundle = safe_extract(candidate, root / 'bundle')
require(hashes(bundle) == before, 'pra294-c59 extraction mismatch')
shutil.rmtree(bundle / 'dfthcsos')
shutil.copytree(generated / 'dfthcsos', bundle / 'dfthcsos')
require(hashes(bundle) == target, 'Rollback bundle differs from pra293-fused-invsqrt pins')
fallback = build_zip(bundle, root / 'rollback.zip')
after = inventory(fallback)
require(after == target, 'Rollback archive member mismatch')
equal = []
with zipfile.ZipFile(candidate) as original, zipfile.ZipFile(fallback) as output:
    for name in delta['unchanged']:
        require(original.read(name) == output.read(name), f'Non-chemistry bytes changed: {name}')
        equal.append(name)
print('BYTE-EQUAL non-chemistry members:', equal, flush=True)
with zipfile.ZipFile(parent) as prior, zipfile.ZipFile(fallback) as output:
    for name in sorted(target):
        require(prior.read(name) == output.read(name), f'Rollback differs from pra293-fused-invsqrt: {name}')
output_hash = digest(fallback)
require(output_hash == parent_hash, f'Rollback zip {output_hash} is not archive-identical to pra293-fused-invsqrt')
require(digest(candidate) == candidate_hash and digest(parent) == parent_hash, 'Source archive changed')
receipt = dict(source_commit=pin, started_utc=started, finished_utc=datetime.now(timezone.utc).isoformat(),
               source_zip=str(candidate), source_zip_sha256=candidate_hash,
               target_zip=str(parent), target_zip_sha256=parent_hash,
               output_zip=str(fallback), output_zip_sha256=output_hash, output_equals_target_zip=True,
               byte_equal_non_chemistry=equal, delta=delta, before=before, after=after,
               source_archives_unchanged=True)
(root / 'member-hashes.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2), flush=True)
print('PASS: only dfthcsos/ changed; invsqrt.kmb and dqi.kmb byte-equal; output zip == pra293-fused-invsqrt', flush=True)
PY
