#!/usr/bin/env bash
# PRA-293 dqi-only rollback: pra293-fused-invsqrt -> pra281-invsqrt-port (#62), i.e. the fused
# dqi.kmb back to the pra261-schur Schur dqi.kmb, with the port invsqrt and all 26 chemistry members kept.
# The Schur dqi is regenerated from a git archive of main c72649c (tasks.dqi.generate_schur,
# the generator in pra281-invsqrt-port's G5); no circuit is copied from an old zip.
# pra281-invsqrt-port's own invsqrt-only rollback (#62, rollback.py) continues to submission-008.
# Usage: bash rehearsal-command.sh [OUTPUT_ROOT]   (OUTPUT_ROOT must not exist)
set -euo pipefail
ROOT="${1:-/home/cld-main/work/vqcc-data/pra293-fused-invsqrt-rollback-20261027}"
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

pin = 'c72649c261fa38db3f36cacc832f47e7b5775fac'
root, repo = Path(sys.argv[1]), Path(sys.argv[2])
fused = Path('/home/cld-main/work/vqcc-data/pra293-fused-invsqrt/pra293-fused-invsqrt.zip')
port = Path('/home/cld-main/work/vqcc-data/pra284/pra281-invsqrt-port.zip')
package = Path('/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation')
fused_hash = '22258bb57f1a711336567cb8771c7f88936d903af7727ab0bbd993fb72e5f27d'
port_hash = '5c8db085d18872b17dc16890a2afd6ea8b3c63d3dc513b853ba0ac20b797cecd'
rustad_hash = '8e2918400fd033440d350d4af76bc4bdfca3787cdf411dcbb974f03d3b4f8f21'
port_invsqrt = '17fc223d79d3f1f15ef448389072209972b373403dd0a45352f4fe7eaff541ad'
fused_dqi = '7beea291a5de36ef2b4fb50585b2f8d7cce02d3c575b491cf5dcc93e9d9655f6'
schur_dqi = '1a1c60ae30f506ec5d05728d893f63d2e0c4952b0145af2081236bfef1e18f48'

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
require(digest(fused) == fused_hash, 'Wrong pra293-fused-invsqrt archive; no rollback performed')
require(digest(port) == port_hash, 'Wrong pra281-invsqrt-port archive')
target_manifest = manifest('ledger/manifests/candidates/pra281-invsqrt-port.json')
require((target_manifest['zip_sha256'], target_manifest['parent_candidate_id']) == (port_hash, 'pra280-rustad'),
        'pra281-invsqrt-port lineage')
target = members(target_manifest)
require(target['dqi.kmb'] == schur_dqi and target['invsqrt.kmb'] == port_invsqrt, 'pra281-invsqrt-port pins')
require(members(manifest('ledger/manifests/candidates/pra261-schur.json'))['dqi.kmb'] == schur_dqi,
        'pra261-schur dqi pin differs')
sub8 = manifest('ledger/manifests/submissions/submission-008.json')
require((sub8['source_candidate_id'], sub8['zip_sha256']) == ('pra280-rustad', rustad_hash), 'submission-008 lineage')
require(sorted(n for n in target if members(sub8)[n] != target[n]) == ['invsqrt.kmb'],
        'pra281-invsqrt-port is not submission-008 with only invsqrt changed')
before = inventory(fused)
require(inventory(port) == target, 'pra281-invsqrt-port member mismatch')
require(set(before) == set(target), 'Member sets differ; not a dqi-only rollback')
changed = sorted(n for n in target if before[n] != target[n])
require(changed == ['dqi.kmb'] and before['dqi.kmb'] == fused_dqi, f'Unexpected archive delta {changed}')
delta = dict(restored_in_rollback=changed, removed_in_rollback=[], added_in_rollback=[],
             unchanged=sorted(n for n in target if before[n] == target[n]))
print('INPUTS VERIFIED', json.dumps({'pra293-fused-invsqrt': fused_hash, 'pra281-invsqrt-port': port_hash, 'pin': pin}), flush=True)
print('DELTA', json.dumps({'restored_in_rollback': changed, 'unchanged': len(delta['unchanged'])}), flush=True)

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
run(['uv', 'run', '--frozen', 'python', '-m', 'tasks.dqi.generate_schur', '--out', generated], source)
require(hashes(generated) == {'dqi.kmb': schur_dqi}, 'Regenerated dqi differs from the pra261-schur pin')
print('REGENERATED dqi.kmb matches pra261-schur:', schur_dqi, flush=True)

sys.path.insert(0, str(source))
from ledger.archive import safe_extract, build_zip
bundle = safe_extract(fused, root / 'bundle')
require(hashes(bundle) == before, 'pra293-fused-invsqrt extraction mismatch')
shutil.copyfile(generated / 'dqi.kmb', bundle / 'dqi.kmb')
require(hashes(bundle) == target, 'Rollback bundle differs from pra281-invsqrt-port pins')
fallback = build_zip(bundle, root / 'rollback.zip')
after = inventory(fallback)
require(after == target, 'Rollback archive member mismatch')
equal = []
with zipfile.ZipFile(fused) as original, zipfile.ZipFile(fallback) as output:
    for name in delta['unchanged']:
        require(original.read(name) == output.read(name), f'Non-dqi bytes changed: {name}')
        equal.append(name)
print('BYTE-EQUAL non-dqi members:', len(equal), flush=True)
with zipfile.ZipFile(port) as prior, zipfile.ZipFile(fallback) as output:
    for name in sorted(target):
        require(prior.read(name) == output.read(name), f'Rollback differs from pra281-invsqrt-port: {name}')
output_hash = digest(fallback)
require(output_hash == port_hash, f'Rollback zip {output_hash} is not archive-identical to pra281-invsqrt-port')
require(digest(fused) == fused_hash and digest(port) == port_hash, 'Source archive changed')
receipt = dict(source_commit=pin, started_utc=started, finished_utc=datetime.now(timezone.utc).isoformat(),
               source_zip=str(fused), source_zip_sha256=fused_hash,
               target_zip=str(port), target_zip_sha256=port_hash,
               output_zip=str(fallback), output_zip_sha256=output_hash,
               output_equals_target_zip=True, regenerated_dqi_sha256=schur_dqi,
               byte_equal_non_dqi=equal, delta=delta, before=before, after=after,
               source_archives_unchanged=True)
(root / 'member-hashes.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2), flush=True)
print('PASS: only dqi.kmb changed; 27 other members byte-equal; output zip == pra281-invsqrt-port', flush=True)
PY
