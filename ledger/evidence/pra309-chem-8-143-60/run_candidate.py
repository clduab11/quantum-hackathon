"""Build PRA-321's exact zip on the submission-010 parent and run G0–G5.

Example: TMPDIR=/home/cld-main/work/vqcc-data/pra309-chem-8-143-60/tmp \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 UV_NO_SYNC=1 PYTHONPATH=. \
  uv run python ledger/evidence/pra309-chem-8-143-60/run_candidate.py
The zip is pra294-c59 (submission-010) with every dfthcsos/ member replaced by
tasks.dfthcsos.b143 output. G5 regenerates all three tasks from the committed
generators. Neither zip is a generator input. A mismatch or failed gate exits
nonzero; no upload occurs. TMPDIR must be a directory this process keeps until
the pipeline returns (D-PRA294-01).

VQCC_DATA selects the data root (default /home/cld-main/work/vqcc-data). When
the manifest already exists, a conflicting --generator-commit is rejected:
run_pipeline is not allowed to report success for a commit the manifest did
not check. Repeat G5 for another commit with `python -m ledger.gates.runner
rerun`, which appends a record and leaves the manifest's generator_commit
unchanged. A missing zip is rebuilt with build() and its SHA-256 is checked
against the manifest before any gate runs. An empty gate result does not
replace an existing pipeline.json.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from ledger.archive import build_zip, safe_extract
from ledger.gates.runner import load_config, run_pipeline, start_candidate
from ledger.run_manifest import Provenance, read_manifest, sha256_file, write_manifest

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA = Path('/home/cld-main/work/vqcc-data')
CANDIDATE = 'pra309-chem-8-143-60'
PARENT = 'pra294-c59'
# Files the three generators execute. Other dirty paths in this shared worktree are not inputs.
GENERATOR_PATHS = (
    'tasks/dfthcsos/b143.py',
    'tasks/dfthcsos/full_xor',
    'tasks/dfthcsos/generate.py',
    'tasks/invsqrt/public_port',
    'tasks/dqi',
)


def data_root():
    """Competition-data root. VQCC_DATA wins over the machine default."""
    return Path(os.environ.get('VQCC_DATA', DEFAULT_DATA))


def candidate_paths(root=ROOT):
    data = data_root()
    return {
        'data': data,
        'parent_zip': data / PARENT / f'{PARENT}.zip',
        'zip': data / CANDIDATE / f'{CANDIDATE}.zip',
        'manifest': root / f'ledger/manifests/candidates/{CANDIDATE}.json',
        'config': root / f'configs/gates/{CANDIDATE}.yaml',
        'parent_manifest': root / f'ledger/manifests/candidates/{PARENT}.json',
        'pipeline': Path(__file__).resolve().parent / 'pipeline.json',
    }


def require_generator_paths(commit):
    """Refuse a pin unless those paths match the commit exactly."""
    if not re.fullmatch(r'[0-9a-f]{40}', commit or ''):
        raise ValueError(f'generator commit {commit!r} is not a clean 40-hex commit')
    proc = subprocess.run(
        ['git', 'diff', '--exit-code', commit, '--', *GENERATOR_PATHS],
        cwd=ROOT, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise ValueError(
            f'generator paths differ from {commit}; not pinning over a real generator edit\n'
            f'{proc.stdout[-2000:]}')


def build(parent, loc):
    from tasks.dfthcsos import b143
    if sha256_file(loc['parent_zip']) != parent.zip_sha256:
        raise ValueError(f"{loc['parent_zip']} does not match the {PARENT} manifest")
    loc['zip'].parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pra321-', dir=loc['zip'].parent) as tmp:
        bundle = safe_extract(loc['parent_zip'], Path(tmp) / 'bundle')
        shutil.rmtree(bundle / 'dfthcsos')
        report = b143.generate(Path(tmp) / 'chem', data=loc['data'])
        shutil.copytree(Path(tmp) / 'chem' / 'dfthcsos', bundle / 'dfthcsos')
        build_zip(bundle, loc['zip'])
    return report


def _summary(manifest, records, started, loc):
    return dict(gates=[dict(gate=r.gate, status=r.status, reason=r.reason) for r in records],
                seconds=time.monotonic() - started, shipping_problems=manifest.shipping_problems(),
                geometric_mean=manifest.geometric_mean, zip_sha256=sha256_file(loc['zip']),
                generator_commit=manifest.generator_commit)


def _reject_conflicting_generator_commit(manifest, requested):
    """An existing manifest must not ignore a different --generator-commit.

    run_pipeline skips a gate that already PASSed, so a new commit would be
    reported as success without a rebuild check. Refuse here. A deliberate
    repeat goes through ledger.gates.runner rerun, which appends G5 and does
    not change the manifest's generator_commit.
    """
    if not requested or requested == manifest.generator_commit:
        return
    raise ValueError(
        f'--generator-commit {requested} != manifest generator_commit '
        f'{manifest.generator_commit}; refusing to report success without a G5 '
        f'check of that commit. Repeat G5 with `python -m ledger.gates.runner rerun` '
        f'so the manifest identity stays unchanged.')


def _rebuild_missing_zip(parent, manifest, loc):
    """Rebuild through build() only. Do not take the exclusive manifest-writing path."""
    build(parent, loc)
    actual = sha256_file(loc['zip'])
    if actual != manifest.zip_sha256:
        raise ValueError(
            f"rebuilt {loc['zip']} SHA-256 {actual} != manifest zip_sha256 {manifest.zip_sha256}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Print paths; write nothing and run no gates.')
    parser.add_argument('--generator-commit',
                        help='Clean commit whose generator paths match the worktree. '
                             'Required when other tickets leave this shared worktree dirty, '
                             'because a -dirty generator_commit cannot pass G5. '
                             'On an existing manifest this must equal generator_commit; '
                             'a mismatch is rejected.')
    args = parser.parse_args(argv)
    loc = candidate_paths()
    if args.dry_run:
        print(json.dumps({'parent_zip': str(loc['parent_zip']), 'zip': str(loc['zip']),
                          'manifest': str(loc['manifest']), 'config': str(loc['config']),
                          'data': str(loc['data']), 'gates': 'G0-G5; no waivers'}, indent=2))
        return
    config = load_config(loc['config'])
    parent = read_manifest(loc['parent_manifest'])
    if loc['manifest'].exists():
        manifest = read_manifest(loc['manifest'])
        _reject_conflicting_generator_commit(manifest, args.generator_commit)
        if not loc['zip'].exists():
            _rebuild_missing_zip(parent, manifest, loc)
    else:
        if loc['zip'].exists():
            raise FileExistsError('zip exists without manifest; inspect before retrying')
        report = build(parent, loc)
        provenance = {task: record.provenance for task, record in parent.tasks.items()}
        provenance['dfthcsos'] = Provenance(
            licence='Apache-2.0',
            parent_url='https://www.kaggle.com/datasets/somejoint/qcc-our-chemistry-b143-c60-xor2',
            notes=('Declared non-circuit factor submission.npz SHA-256 '
                   'aef36d39b83bbbf696e909884218f6c02f067baef14a29de1c41306bc1f6395b, '
                   'somejoint/qcc-our-chemistry-b143-c60-xor2 version 1, licence field Apache 2.0, '
                   'copied under D-PRA211-05. The fit is not in the published source. '
                   'All 15 circuits regenerated by the ported full-XOR J=5 compiler '
                   '(notebook somejoint/quantum-circuits-22-67-local-gm-full-xor-chem v18, Apache-2.0) '
                   'from committed plans; no certificate or circuit input. '
                   'Full rows: ledger/manifests/inputs/pra309-chem-8-143-60.json; notices/30-dfthcsos.txt.'))
        manifest = start_candidate(
            loc['zip'], CANDIDATE, provenance, parent_candidate_id=PARENT,
            salt_label=config.salt_label,
            notes=('PRA-321: submission-010 (pra294-c59) with only the dfthcsos/ files changed '
                   'to the (8,143,60) factor through the full-XOR J=5 compiler. '
                   'No salt/seed search or upload.'))
        for task in ('invsqrt', 'dqi'):
            if manifest.tasks[task].files != parent.tasks[task].files:
                raise ValueError(f'{task} files differ from {PARENT}')
        expected = {name: row['sha256'] for name, row in report['files'].items()}
        if manifest.tasks['dfthcsos'].files != expected:
            raise ValueError('dfthcsos files are not the b143 build alone')
        if args.generator_commit:
            require_generator_paths(args.generator_commit)
            manifest.generator_commit = args.generator_commit
        elif manifest.generator_commit.endswith('-dirty') or manifest.generator_commit == 'unknown':
            raise ValueError(
                f'generator_commit is {manifest.generator_commit}; pass --generator-commit '
                'of a clean commit whose generator paths match this worktree')
        write_manifest(manifest, loc['manifest'], exclusive=True)
    started = time.monotonic()
    records = run_pipeline(manifest, loc['zip'], config, repo=ROOT, manifest_file=loc['manifest'],
                           package_root=loc['data'])
    if records:
        summary = _summary(manifest, records, started, loc)
        loc['pipeline'].write_text(json.dumps(summary, indent=2) + '\n')
    elif loc['pipeline'].exists():
        summary = json.loads(loc['pipeline'].read_text())
        summary = dict(summary, preserved_pipeline=True)
    else:
        summary = _summary(manifest, records, started, loc)
    print(json.dumps(summary, indent=2), flush=True)
    if manifest.shipping_problems():
        raise SystemExit(1)


if __name__ == '__main__':
    main()
