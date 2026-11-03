"""Build submission-011 with only invsqrt replaced, then run the real gates.

Run from the repository root, with PYTHONPATH=. and a persistent TMPDIR.
No upload occurs. Existing manifests keep their identity and gate history.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from ledger.archive import build_zip, safe_extract
from ledger.gates.runner import load_config, run_pipeline, start_candidate
from ledger.run_manifest import Provenance, read_manifest, sha256_file, write_manifest
from tasks.invsqrt.vendored.generate import INPUT_PATH, PIN, SHA256, stage

ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = 'pra325-invsqrt-vendored-63q'
PARENT = 'pra309-chem-8-143-60'
PARENT_SHA256 = 'a710cab21a8bac7ff552944ca48e8afb4e0fe4c98e0be5fd2e86be32b79c01ac'


def build(data, output, parent):
    parent_zip = data / PARENT / f'{PARENT}.zip'
    if sha256_file(parent_zip) != PARENT_SHA256 or parent.zip_sha256 != PARENT_SHA256:
        raise ValueError('parent zip or manifest is not the pinned submission-011')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='assemble-', dir=output.parent) as tmp:
        bundle = safe_extract(parent_zip, Path(tmp) / 'bundle')
        stage(data / INPUT_PATH, bundle)
        build_zip(bundle, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stop-after', choices=['G0', 'G1', 'G2', 'G3', 'G4', 'G5'], default='G5')
    args = parser.parse_args()
    data = Path(os.environ.get('VQCC_DATA', '/home/cld-main/work/vqcc-data'))
    output = data / CANDIDATE / f'{CANDIDATE}.zip'
    manifest_path = ROOT / 'ledger/manifests/candidates' / f'{CANDIDATE}.json'
    parent = read_manifest(ROOT / 'ledger/manifests/candidates' / f'{PARENT}.json')
    config = load_config(ROOT / 'configs/gates' / f'{CANDIDATE}.yaml')
    if manifest_path.exists():
        manifest = read_manifest(manifest_path)
        if not output.exists():
            build(data, output, parent)
        if sha256_file(output) != manifest.zip_sha256:
            raise ValueError('candidate zip differs from its recorded identity')
    else:
        # G5 must use exactly this committed implementation, not unrelated dirty files.
        paths = ['tasks/invsqrt/vendored', 'tasks/dqi', 'tasks/dfthcsos',
                 'configs/gates/' + CANDIDATE + '.yaml', str(Path(__file__).relative_to(ROOT))]
        if subprocess.check_output(['git', 'status', '--porcelain', '--', *paths], cwd=ROOT):
            raise ValueError('commit the candidate implementation before recording its identity')
        build(data, output, parent)
        provenance = {task: row.provenance for task, row in parent.tasks.items()}
        provenance['invsqrt'] = Provenance(
            licence=PIN['licence'], parent_url=PIN['source_url'],
            notes=('Unchanged vendored circuit under D-PRA341-01. mrmeows dataset v8 '
                   'circuits/invsqrt.kmb, SHA-256 ' + SHA256 + '. '
                   'Licence ACCEPT: PRA-346, comment ' + PIN['licence_record_comment'] + '. '
                   'Five upstream credits and LICENSE preserved in tasks/invsqrt/vendored/. '
                   'No own-generator claim; no Schur or k256 artifact.'))
        manifest = start_candidate(output, CANDIDATE, provenance,
            parent_candidate_id=PARENT, salt_label=config.salt_label, repo=ROOT,
            notes='PRA-325: submission-011 with only invsqrt.kmb changed. Fixed salt, full shots; no upload.')
        manifest.generator_commit = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        for task in ('dqi', 'dfthcsos'):
            if manifest.tasks[task].files != parent.tasks[task].files:
                raise ValueError(f'{task} differs from the parent')
        if manifest.tasks['invsqrt'].files != {'invsqrt.kmb': SHA256}:
            raise ValueError('invsqrt differs from the accepted source')
        write_manifest(manifest, manifest_path, exclusive=True)
    records = run_pipeline(manifest, output, config, repo=ROOT,
        manifest_file=manifest_path, package_root=data, stop_after=args.stop_after)
    report = {'zip_path': str(output), 'zip_sha256': sha256_file(output),
              'zip_size': output.stat().st_size, 'geometric_mean': manifest.geometric_mean,
              'gates': [{'gate': r.gate, 'status': r.status, 'reason': r.reason} for r in records],
              'shipping_problems': manifest.shipping_problems()}
    if records:
        Path(__file__).with_name('pipeline.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)
    if any(r.status != 'PASS' for r in records) or (args.stop_after == 'G5' and manifest.shipping_problems()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
