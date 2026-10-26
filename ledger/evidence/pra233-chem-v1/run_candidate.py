"""PRA-247 execution receipt. Run from the repo root with PYTHONPATH=.

OPENBLAS_NUM_THREADS=1 PYTHONPATH=. uv run python \
    ledger/evidence/pra233-chem-v1/run_candidate.py

Full fixed-salt checks, no waivers. The report wrapper only saves the original
harness report (including elapsed seconds); it returns it unchanged.
"""
import json
import shutil
import time
from pathlib import Path

from harness import score_local
from ledger.archive import build_zip
from ledger.gates.runner import load_config, run_pipeline, start_candidate
from ledger.run_manifest import Provenance, read_manifest, sha256_file, write_manifest

ROOT = Path(__file__).resolve().parents[3]
DATA = Path('/home/cld-main/work/vqcc-data')
EVIDENCE = ROOT / 'ledger/evidence/pra233-chem-v1'
BUNDLE = DATA / 'pra247-chem-v1/bundle'
ZIP = DATA / 'pra247-chem-v1/pra233-chem-v1.zip'
MANIFEST = ROOT / 'ledger/manifests/candidates/pra233-chem-v1.json'
GENERATOR = '215309ccfa7cb452f48640b465ff1b2f00fee4f7'


def main():
    if ZIP.exists() or MANIFEST.exists():
        raise FileExistsError('candidate already exists; inspect its recorded gates before resuming')
    parent = read_manifest(ROOT / 'ledger/manifests/submissions/submission-004.json')
    for task in ('dqi', 'invsqrt'):
        assert sha256_file(BUNDLE / f'{task}.kmb') == parent.tasks[task].files[f'{task}.kmb']
    build_zip(BUNDLE, ZIP)
    provenance = {task: record.provenance for task, record in parent.tasks.items()}
    provenance['dfthcsos'] = Provenance(
        licence='Apache-2.0',
        parent_url='https://www.kaggle.com/datasets/dmitriigluzdov/vqcc-femoco-public-factorization?datasetVersionNumber=8',
        notes='Gluzdov v8 factor, declared by PRA-245 and SHA-256-pinned in default.yaml. '
              'Non-circuit NPZ copied under D-PRA211-05; all ANGLE circuits regenerated '
              'by the merged PRA-232 ANF builder. Method parents: notices/30-dfthcsos.txt. '
              '11 bits, J=10, direct traversal, scratch=8, pebble_degree=4; D-PRA247-02.')
    config = load_config()
    manifest = start_candidate(ZIP, 'pra233-chem-v1', provenance,
        parent_candidate_id='pra233-2-dqi-q881', salt_label=config.salt_label,
        notes='PRA-247 J=10 chemistry candidate; parent is submission-004/source candidate. '
              'Published generator tree eb1011ee639e766a737b5ae4851dbdb74bf7bdd4 '
              'matches local 67c1d22. No upload; John Wick submits under R-P2-2.')
    manifest.generator_commit = GENERATOR
    write_manifest(manifest, MANIFEST)
    original_report = score_local.report

    def save_report(name, result, seconds, baseline=None):
        report = original_report(name, result, seconds, baseline)
        (EVIDENCE / f'{name}-full.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({k: report[k] for k in ('task', 'status', 'seconds', 'cost', 'ratio')}), flush=True)
        return report

    score_local.report = save_report
    started = time.monotonic()
    records = run_pipeline(manifest, ZIP, config, manifest_file=MANIFEST, package_root=DATA)
    summary = {'gates': [{'gate': r.gate, 'status': r.status, 'reason': r.reason} for r in records],
               'seconds': time.monotonic() - started, 'shipping_problems': manifest.shipping_problems(),
               'zip_sha256': sha256_file(ZIP), 'zip_bytes': ZIP.stat().st_size}
    (EVIDENCE / 'pipeline.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2), flush=True)
    if manifest.shipping_problems():
        raise SystemExit(1)
    destination = DATA / 'queue' / ZIP.name
    if destination.exists():
        raise FileExistsError(destination)
    shutil.copyfile(ZIP, destination)
    assert sha256_file(destination) == manifest.zip_sha256


if __name__ == '__main__':
    main()
