"""Roll local candidate use back from pra281-invsqrt-port to its parent pra280-rustad.

Rollback (one command, from the checkout whose queue lists the candidate):
  PYTHONPATH=. uv run python ledger/evidence/pra281-invsqrt-port/rollback.py --repo .
It withdraws the candidate's queue pointer (ledger/queue/<id>.json and the ignored queue zip copy),
then selects the parent explicitly and checks it: manifest shipping_problems() == [], archive SHA-256
equal to the manifest, config present, and only invsqrt different from the candidate. Selection is
always explicit (`ledger.scorecard reserve/submit --candidate <manifest> --zip <archive>`), so the
printed parent arguments are what any later reservation must use. Decisions, manifests, evidence and
reservations are never touched; the command makes no reservation, upload or network call.

Rehearsal in disposable staging (git archive of --ref plus the ignored queue zip copy):
  PYTHONPATH=. uv run python ledger/evidence/pra281-invsqrt-port/rollback.py --rehearse --ref HEAD
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

from ledger.run_manifest import read_manifest, sha256_file

ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = 'pra281-invsqrt-port'
PARENT = 'pra280-rustad'
PARENT_CONFIG = 'configs/gates/pra280-rustad.yaml'
PARENT_ZIP = Path('/home/cld-main/work/vqcc-data/pra280/pra280-rustad.zip')
CANDIDATE_ZIP = Path('/home/cld-main/work/vqcc-data/pra284/pra281-invsqrt-port.zip')
# Everything that must survive a rollback byte-for-byte (the append-only records).
WATCHED = ['docs/decisions', 'ledger/manifests', 'ledger/evidence', 'configs/gates', 'notices']


def snapshot(repo, prefixes):
    files = {}
    for prefix in prefixes:
        for path in sorted((repo / prefix).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                files[path.relative_to(repo).as_posix()] = sha256_file(path)
    return files


def zip_members(path):
    with zipfile.ZipFile(path) as archive:
        return {i.filename: hashlib.sha256(archive.read(i)).hexdigest() for i in archive.infolist()}


def rollback(repo, parent_zip=PARENT_ZIP, candidate_zip=CANDIDATE_ZIP):
    """Withdraw the candidate's queue pointer and select the parent; raise if anything is off."""
    queue = repo / 'ledger/queue'
    withdrawn = []
    for name in (f'{CANDIDATE}.json', f'{CANDIDATE}.zip'):
        if (queue / name).exists():
            (queue / name).unlink()
            withdrawn.append(f'ledger/queue/{name}')
    if not withdrawn:
        raise SystemExit(f'{CANDIDATE} has no queue pointer under {queue}; nothing to withdraw')
    manifest_path = repo / f'ledger/manifests/candidates/{PARENT}.json'
    parent = read_manifest(manifest_path)
    candidate = read_manifest(repo / f'ledger/manifests/candidates/{CANDIDATE}.json')
    problems = parent.shipping_problems()
    if problems:
        raise SystemExit(f'{PARENT} may not ship: {problems}')
    if not (repo / PARENT_CONFIG).is_file():
        raise SystemExit(f'{PARENT_CONFIG} is missing')
    if sha256_file(parent_zip) != parent.zip_sha256:
        raise SystemExit(f'{parent_zip} does not match the {PARENT} manifest')
    changed = sorted(t for t in parent.tasks if parent.tasks[t].files != candidate.tasks[t].files)
    if changed != ['invsqrt']:
        raise SystemExit(f'expected only invsqrt to differ from {PARENT}, got {changed}')
    parent_members, candidate_members = zip_members(parent_zip), zip_members(candidate_zip)
    differing = sorted(n for n in parent_members.keys() | candidate_members.keys()
                       if parent_members.get(n) != candidate_members.get(n))
    if differing != ['invsqrt.kmb']:
        raise SystemExit(f'expected only invsqrt.kmb to differ between the zips, got {differing}')
    if parent_members['invsqrt.kmb'] != parent.tasks['invsqrt'].files['invsqrt.kmb']:
        raise SystemExit('parent zip invsqrt.kmb does not match its manifest')
    return {
        'withdrawn': withdrawn,
        'selected': {
            'candidate_id': parent.candidate_id,
            'manifest': f'ledger/manifests/candidates/{PARENT}.json',
            'manifest_sha256': sha256_file(manifest_path),
            'config': PARENT_CONFIG,
            'archive': str(parent_zip),
            'archive_sha256': parent.zip_sha256,
            'shipping_problems': problems,
            'geometric_mean': parent.geometric_mean,
            'reserve_args': f'--candidate ledger/manifests/candidates/{PARENT}.json',
            'submit_args': f'--candidate ledger/manifests/candidates/{PARENT}.json --zip {parent_zip}',
        },
        'invsqrt': {'withdrawn': candidate.tasks['invsqrt'].files['invsqrt.kmb'],
                    'restored': parent.tasks['invsqrt'].files['invsqrt.kmb'],
                    'ratio_withdrawn': candidate.tasks['invsqrt'].ratio,
                    'ratio_restored': parent.tasks['invsqrt'].ratio},
        'unchanged_tasks': {t: parent.tasks[t].files == candidate.tasks[t].files for t in ('dqi', 'dfthcsos')},
    }


def rehearse(ref):
    commit = subprocess.check_output(['git', 'rev-parse', '--verify', f'{ref}^{{commit}}'],
                                     cwd=ROOT, text=True).strip()
    with tempfile.TemporaryDirectory(prefix='pra284-rollback-') as tmp:
        staging = Path(tmp) / 'repo'
        staging.mkdir()
        archive = subprocess.run(['git', 'archive', '--format=tar', commit], cwd=ROOT,
                                 check=True, capture_output=True).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(staging, filter='data')
        queue_copy = ROOT / f'ledger/queue/{CANDIDATE}.zip'
        if queue_copy.exists():
            shutil.copyfile(queue_copy, staging / f'ledger/queue/{CANDIDATE}.zip')
        before_queue = snapshot(staging, ['ledger/queue'])
        before = snapshot(staging, WATCHED)
        result = rollback(staging)
        after_queue = snapshot(staging, ['ledger/queue'])
        after = snapshot(staging, WATCHED)
        removed = sorted(before_queue.keys() - after_queue.keys())
        if removed != sorted(result['withdrawn']):
            raise SystemExit(f'queue changes {removed} differ from the withdrawal')
        if any(before_queue[k] != after_queue[k] for k in after_queue) or after_queue.keys() - before_queue.keys():
            raise SystemExit('other queue entries changed')
        if before != after:
            raise SystemExit('a decision, manifest, evidence, config or notice file changed')
        reservations = sorted(k for k in after if k.startswith('ledger/manifests/reservations/'))
        return {
            'source_commit': commit,
            'staging': 'git archive of source_commit in a temporary directory, deleted afterwards',
            **result,
            'queue_before': before_queue,
            'queue_after': after_queue,
            'preserved_records': {
                'files': len(after),
                'sha256_of_listing': hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest(),
                'decision': {k: v for k, v in after.items() if k.endswith('D-PRA281-01.md')},
                'candidate_manifest': {k: v for k, v in after.items()
                                       if k.endswith(f'candidates/{CANDIDATE}.json')},
                'reservation_files_unchanged': len(reservations),
            },
            'reservation_or_upload': 'none',
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', type=Path, default=ROOT, help='checkout to roll back (default: this one)')
    parser.add_argument('--rehearse', action='store_true', help='run in disposable staging instead')
    parser.add_argument('--ref', default='HEAD', help='commit to stage for --rehearse')
    args = parser.parse_args()
    result = rehearse(args.ref) if args.rehearse else rollback(args.repo.resolve())
    json.dump(result, sys.stdout, indent=2)
    print()


if __name__ == '__main__':
    main()
