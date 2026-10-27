"""Build PRA-284's exact zip on the pra280-rustad parent and run G0–G5; resume on rerun.

Example: OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=. \
  uv run --group gpu python ledger/evidence/pra281-invsqrt-port/run_candidate.py --dry-run
The zip is the parent's hash-checked zip with only invsqrt.kmb replaced by the clean-rebuild
port circuit (SHA-256 17fc223d…). G5 regenerates all three tasks from the committed generators;
neither zip is a generator input. A mismatch or failed gate exits nonzero; no upload occurs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
import zipfile

from ledger.archive import build_zip, safe_extract
from ledger.gates.runner import load_config, run_pipeline, start_candidate
from ledger.run_manifest import Provenance, read_manifest, sha256_file, write_manifest

ROOT = Path(__file__).resolve().parents[3]
DATA = Path('/home/cld-main/work/vqcc-data')
CANDIDATE = 'pra281-invsqrt-port'
PARENT = 'pra280-rustad'
PARENT_ZIP = DATA / 'pra280' / f'{PARENT}.zip'
# Clean rebuild 1 (clean-rebuilds.json), first packed into the superseded PRA-250-based zip.
PORT_SOURCE = DATA / 'queue' / 'pra281-invsqrt-port.pra250-base-72696370.zip'
PORT_SHA256 = '17fc223d79d3f1f15ef448389072209972b373403dd0a45352f4fe7eaff541ad'
ZIP = DATA / 'pra284' / f'{CANDIDATE}.zip'
MANIFEST = ROOT / f'ledger/manifests/candidates/{CANDIDATE}.json'
CONFIG = ROOT / 'configs/gates/pra281-invsqrt-port.yaml'


def build(parent):
    if sha256_file(PARENT_ZIP) != parent.zip_sha256:
        raise ValueError(f'{PARENT_ZIP} does not match the {PARENT} manifest')
    with zipfile.ZipFile(PORT_SOURCE) as archive:
        port = archive.read('invsqrt.kmb')
    if hashlib.sha256(port).hexdigest() != PORT_SHA256:
        raise ValueError('port circuit hash differs from the clean rebuilds')
    with tempfile.TemporaryDirectory(prefix='pra284-') as tmp:
        bundle = safe_extract(PARENT_ZIP, Path(tmp) / 'bundle')
        (bundle / 'invsqrt.kmb').write_bytes(port)
        build_zip(bundle, ZIP)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Print paths; write nothing and run no gates.')
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({'parent_zip': str(PARENT_ZIP), 'port_source': str(PORT_SOURCE), 'zip': str(ZIP),
                          'manifest': str(MANIFEST), 'config': str(CONFIG), 'gates': 'G0-G5; no waivers'},
                         indent=2))
        return
    config = load_config(CONFIG)
    parent = read_manifest(ROOT / f'ledger/manifests/candidates/{PARENT}.json')
    if MANIFEST.exists():
        manifest = read_manifest(MANIFEST)
    else:
        if ZIP.exists():
            raise FileExistsError('zip exists without manifest; inspect before retrying')
        build(parent)
        provenance = {task: record.provenance for task, record in parent.tasks.items()}
        provenance['invsqrt'] = Provenance(licence='Apache-2.0',
            parent_url='https://www.kaggle.com/code/dmitriigluzdov/quantum-circuit-compilation-from-source?scriptVersionId=361726742',
            notes='Gluzdov v7 recipe port already recorded in D-PRA249-01 and notices/10-invsqrt.txt. Coefficients freshly enumerated on CUDA; committed arithmetic, affine compiler and angle calibration rebuild every circuit byte. No circuit, fitted table, angle file or rewrite file is an input. No new licence check.')
        manifest = start_candidate(ZIP, CANDIDATE, provenance, parent_candidate_id=PARENT,
            salt_label=config.salt_label,
            notes=f'PRA-284 floor candidate; only invsqrt differs from {PARENT}. No reservation or upload; pending review.')
        for task in ('dqi', 'dfthcsos'):
            if manifest.tasks[task].files != parent.tasks[task].files:
                raise ValueError(f'{task} files differ from {PARENT}')
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
