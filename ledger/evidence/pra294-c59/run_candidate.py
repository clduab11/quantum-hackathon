"""Build PRA-294's exact zip on the pra293-fused-invsqrt parent and run G0–G5; resume on rerun.

Example: OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 UV_NO_SYNC=1 PYTHONPATH=. \
  uv run python ledger/evidence/pra294-c59/run_candidate.py --dry-run
The zip is the parent's hash-checked zip with every dfthcsos/ member replaced by
tasks.dfthcsos.c59 output (19 J=4 circuits plus the declared C59 factor). G5
regenerates all three tasks from the committed generators (invsqrt refits on
CUDA); neither zip is a generator input. A mismatch or failed gate exits
nonzero; no upload occurs.
"""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import time

from ledger.archive import build_zip, safe_extract
from ledger.gates.runner import load_config, run_pipeline, start_candidate
from ledger.run_manifest import Provenance, read_manifest, sha256_file, write_manifest

ROOT = Path(__file__).resolve().parents[3]
DATA = Path('/home/cld-main/work/vqcc-data')
CANDIDATE = 'pra294-c59'
PARENT = 'pra293-fused-invsqrt'
PARENT_ZIP = DATA / PARENT / f'{PARENT}.zip'
ZIP = DATA / CANDIDATE / f'{CANDIDATE}.zip'
MANIFEST = ROOT / f'ledger/manifests/candidates/{CANDIDATE}.json'
CONFIG = ROOT / f'configs/gates/{CANDIDATE}.yaml'


def build(parent):
    from tasks.dfthcsos import c59
    if sha256_file(PARENT_ZIP) != parent.zip_sha256:
        raise ValueError(f'{PARENT_ZIP} does not match the {PARENT} manifest')
    ZIP.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pra294-') as tmp:
        bundle = safe_extract(PARENT_ZIP, Path(tmp) / 'bundle')
        shutil.rmtree(bundle / 'dfthcsos')
        report = c59.generate(Path(tmp) / 'chem', data=DATA)
        shutil.copytree(Path(tmp) / 'chem' / 'dfthcsos', bundle / 'dfthcsos')
        build_zip(bundle, ZIP)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Print paths; write nothing and run no gates.')
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({'parent_zip': str(PARENT_ZIP), 'zip': str(ZIP), 'manifest': str(MANIFEST),
                          'config': str(CONFIG), 'gates': 'G0-G5; no waivers'}, indent=2))
        return
    config = load_config(CONFIG)
    parent = read_manifest(ROOT / f'ledger/manifests/candidates/{PARENT}.json')
    if MANIFEST.exists():
        manifest = read_manifest(MANIFEST)
    else:
        if ZIP.exists():
            raise FileExistsError('zip exists without manifest; inspect before retrying')
        report = build(parent)
        provenance = {task: record.provenance for task, record in parent.tasks.items()}
        provenance['dfthcsos'] = Provenance(licence='Apache-2.0',
            parent_url='https://www.kaggle.com/datasets/mrmeows/qcc-1375-open-circuits?datasetVersionNumber=8',
            notes='Declared non-circuit factor circuits/dfthcsos/submission.npz (C59) SHA-256 8229861b3ee22316e144c900737dfc54f7a30ea88de77ff5391f3375d050fa87, licence field Apache 2.0, copied under D-PRA211-05. Lineage: Rustad R10/B129/C60 v1 (licence field Other, recorded not gated, R-P2-6) refit and C60->59 merged by mrmeows. All 19 circuits regenerated with the mrmeows v8 J=4 streamed compiler port (Apache 2.0) from recorded plan seeds; no certificate or circuit input. Full rows: ledger/manifests/inputs/pra294-c59.json; notices/30-dfthcsos.txt.')
        manifest = start_candidate(ZIP, CANDIDATE, provenance, parent_candidate_id=PARENT,
            salt_label=config.salt_label,
            notes=f'PRA-294: {PARENT} (#65) with only the dfthcsos/ files changed to the C59 factor through the J=4 compiler port. No salt/seed search or upload. Adjudicator review required before merge/submission.')
        for task in ('invsqrt', 'dqi'):
            if manifest.tasks[task].files != parent.tasks[task].files:
                raise ValueError(f'{task} files differ from {PARENT}')
        expected = {name: row['sha256'] for name, row in report['files'].items()}
        if manifest.tasks['dfthcsos'].files != expected:
            raise ValueError('dfthcsos files are not the c59 build alone')
        write_manifest(manifest, MANIFEST, exclusive=True)
    started = time.monotonic()
    records = run_pipeline(manifest, ZIP, config, repo=ROOT, manifest_file=MANIFEST, package_root=DATA)
    summary = dict(gates=[dict(gate=r.gate, status=r.status, reason=r.reason) for r in records],
                   seconds=time.monotonic() - started, shipping_problems=manifest.shipping_problems(),
                   geometric_mean=manifest.geometric_mean, zip_sha256=sha256_file(ZIP),
                   generator_commit=manifest.generator_commit)
    (Path(__file__).parent / 'pipeline.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2), flush=True)
    if manifest.shipping_problems():
        raise SystemExit(1)


if __name__ == '__main__':
    main()
