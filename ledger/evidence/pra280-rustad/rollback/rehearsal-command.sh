#!/usr/bin/env bash
# PRA-280 chemistry-only rollback: pra280-rustad (submission-008) -> pra261-schur (submission-007).
# Usage: bash rehearsal-command.sh [OUTPUT_ROOT]   (OUTPUT_ROOT must not exist)
set -euo pipefail
ROOT="${1:-/home/cld-main/work/vqcc-data/pra280-rollback-20261027}"
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

pin = '33c8f82cde158101615b40057eb039649efbdd66'
root, repo = Path(sys.argv[1]), Path(sys.argv[2])
rustad = Path('/home/cld-main/work/vqcc-data/pra280/pra280-rustad.zip')
schur = Path('/home/cld-main/work/vqcc-data/pra261-schur-port/pra261-schur.zip')
factor = Path('/home/cld-main/work/vqcc-data/inputs/thc/femoco_thc_r5.npz')
package = Path('/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation')
rustad_hash = '8e2918400fd033440d350d4af76bc4bdfca3787cdf411dcbb974f03d3b4f8f21'
schur_hash = '9fcb5fe2e82d052568e2c5857965cf87cb51ab0dd1f107ae00c188f8e07b11d5'
factor_hash = '809a992900937425f01a0593803921873f7bb472d590592c378d3ceb23657df5'

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

def manifest(path):
    return json.loads(git('show', f'{pin}:{path}'))

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
require(digest(rustad) == rustad_hash, 'Wrong pra280-rustad archive; no rollback performed')
require(digest(schur) == schur_hash, 'Wrong pra261-schur archive')
require(digest(factor) == factor_hash, 'Wrong Gluzdov v8 factor')
sub7 = manifest('ledger/manifests/submissions/submission-007.json')
sub8 = manifest('ledger/manifests/submissions/submission-008.json')
require((sub7['source_candidate_id'], sub7['zip_sha256']) == ('pra261-schur', schur_hash), 'submission-007 lineage')
require((sub8['source_candidate_id'], sub8['zip_sha256']) == ('pra280-rustad', rustad_hash), 'submission-008 lineage')
target = members(manifest('ledger/manifests/candidates/pra261-schur.json'))
source_pins = members(manifest('ledger/manifests/candidates/pra280-rustad.json'))
require(target == members(sub7) and source_pins == members(sub8), 'Candidate and submission pins disagree')
before = inventory(rustad)
require(before == source_pins, 'pra280-rustad member mismatch')
require(inventory(schur) == target, 'pra261-schur member mismatch')
for name in ('dqi.kmb', 'invsqrt.kmb'):
    require(before[name] == target[name], f'{name} differs between candidates; not a chemistry-only rollback')
require(all(n.startswith('dfthcsos/') for n in set(before) ^ set(target)), 'Non-chemistry member set differs')
delta = dict(
    removed_in_rollback=sorted(set(before) - set(target)),
    restored_in_rollback=sorted(n for n in target if n in before and before[n] != target[n]),
    added_in_rollback=sorted(set(target) - set(before)),
    unchanged=sorted(n for n in target if before.get(n) == target[n]))
require(len(delta['removed_in_rollback']) == 17 and delta['added_in_rollback'] == []
        and len(delta['restored_in_rollback']) == 9 and 'dfthcsos/submission.npz' in delta['restored_in_rollback']
        and delta['unchanged'] == ['dqi.kmb', 'invsqrt.kmb'], 'Unexpected archive delta')
print('INPUTS VERIFIED', json.dumps({'pra280-rustad': rustad_hash, 'pra261-schur': schur_hash,
                                     'factor': factor_hash, 'pin': pin}), flush=True)
print('DELTA', json.dumps(delta, indent=2), flush=True)

root.mkdir(parents=True)
source = root / 'source'
source.mkdir()
with (root / 'source.tar').open('wb') as stream:
    subprocess.run(['git', '-C', str(repo), 'archive', pin], stdout=stream, check=True)
with tarfile.open(root / 'source.tar') as archive:
    archive.extractall(source, filter='data')
run(['uv', 'sync', '--frozen'], source)
run(['uv', 'run', '--frozen', 'python', 'scripts/install_kickmix.py', package], source)
staged = root / 'data' / 'inputs' / 'thc' / 'femoco_thc_r5.npz'
staged.parent.mkdir(parents=True)
shutil.copyfile(factor, staged)
require(digest(staged) == factor_hash, 'Staged factor mismatch')
generated = root / 'generated'
run(['uv', 'run', '--frozen', 'python', '-m', 'tasks.dfthcsos.shipping', '--out', generated,
     '--data', root / 'data', '--batch-size', '10'], source)
chem_target = {n: h for n, h in target.items() if n.startswith('dfthcsos/')}
require(hashes(generated) == chem_target, 'Regenerated chemistry differs from pra261-schur pins')
print('REGENERATED dfthcsos matches pra261-schur:', len(chem_target), 'members', flush=True)

sys.path.insert(0, str(source))
from ledger.archive import safe_extract, build_zip
bundle = safe_extract(rustad, root / 'bundle')
require(hashes(bundle) == before, 'pra280-rustad extraction mismatch')
shutil.rmtree(bundle / 'dfthcsos')
shutil.copytree(generated / 'dfthcsos', bundle / 'dfthcsos')
require(hashes(bundle) == target, 'Rollback bundle differs from pra261-schur pins')
fallback = build_zip(bundle, root / 'rollback.zip')
after = inventory(fallback)
require(after == target, 'Rollback archive member mismatch')
equal = []
with zipfile.ZipFile(rustad) as original, zipfile.ZipFile(fallback) as output:
    for name in ('dqi.kmb', 'invsqrt.kmb'):
        require(original.read(name) == output.read(name), f'Non-chemistry bytes changed: {name}')
        equal.append(name)
        print('BYTE-EQUAL', name, flush=True)
with zipfile.ZipFile(schur) as prior, zipfile.ZipFile(fallback) as output:
    for name in sorted(target):
        require(prior.read(name) == output.read(name), f'Rollback differs from pra261-schur: {name}')
output_hash = digest(fallback)
require(output_hash == schur_hash, f'Rollback zip {output_hash} is not archive-identical to pra261-schur')
require(digest(rustad) == rustad_hash and digest(schur) == schur_hash, 'Source archive changed')
receipt = dict(source_commit=pin, started_utc=started, finished_utc=datetime.now(timezone.utc).isoformat(),
               source_zip=str(rustad), source_zip_sha256=rustad_hash,
               target_zip=str(schur), target_zip_sha256=schur_hash,
               factor=str(factor), factor_sha256=factor_hash,
               output_zip=str(fallback), output_zip_sha256=output_hash,
               output_equals_target_zip=True, byte_equal_non_chemistry=equal,
               delta=delta, before=before, after=after, source_archives_unchanged=True)
(root / 'member-hashes.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2), flush=True)
print('PASS: only dfthcsos changed; dqi and invsqrt byte-equal; output zip == pra261-schur', flush=True)
PY
