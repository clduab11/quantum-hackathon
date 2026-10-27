"""Build PRA-293's exact zip on the pra281-invsqrt-port parent and run G0–G5; resume on rerun.

Example: OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 UV_NO_SYNC=1 PYTHONPATH=. \
  uv run python ledger/evidence/pra293-fused-invsqrt/run_candidate.py --dry-run
The zip is the parent's hash-checked zip with only dqi.kmb replaced by the
tasks/dqi/generate_fused.py output (SHA-256 7beea291…). G5 regenerates all three
tasks from the committed generators (invsqrt refits on CUDA); neither zip is a
generator input. A mismatch or failed gate exits nonzero; no upload occurs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time

from ledger.archive import build_zip, safe_extract
from ledger.gates.runner import load_config, run_pipeline, start_candidate
from ledger.run_manifest import Provenance, read_manifest, sha256_file, write_manifest

ROOT = Path(__file__).resolve().parents[3]
DATA = Path('/home/cld-main/work/vqcc-data')
CANDIDATE = 'pra293-fused-invsqrt'
PARENT = 'pra281-invsqrt-port'
PARENT_ZIP = DATA / 'pra284' / f'{PARENT}.zip'
# The generate_fused.py output already gated in the superseded pra293-fused run.
FUSED_SOURCE = DATA / 'pra293-fused' / 'bundle' / 'dqi.kmb'
FUSED_SHA256 = '7beea291a5de36ef2b4fb50585b2f8d7cce02d3c575b491cf5dcc93e9d9655f6'
ZIP = DATA / CANDIDATE / f'{CANDIDATE}.zip'
MANIFEST = ROOT / f'ledger/manifests/candidates/{CANDIDATE}.json'
CONFIG = ROOT / f'configs/gates/{CANDIDATE}.yaml'


def build(parent):
    if sha256_file(PARENT_ZIP) != parent.zip_sha256:
        raise ValueError(f'{PARENT_ZIP} does not match the {PARENT} manifest')
    fused = FUSED_SOURCE.read_bytes()
    if hashlib.sha256(fused).hexdigest() != FUSED_SHA256:
        raise ValueError('fused dqi hash differs from the generate_fused.py build')
    ZIP.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pra293-') as tmp:
        bundle = safe_extract(PARENT_ZIP, Path(tmp) / 'bundle')
        (bundle / 'dqi.kmb').write_bytes(fused)
        build_zip(bundle, ZIP)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Print paths; write nothing and run no gates.')
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({'parent_zip': str(PARENT_ZIP), 'fused_source': str(FUSED_SOURCE), 'zip': str(ZIP),
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
        provenance['dqi'] = Provenance(licence='Apache-2.0',
            parent_url='https://www.kaggle.com/code/somejoint/quantum-circuits-21-34-local-gm-fused-dqi',
            notes='Kernel 140675727 v12 (Agniv Banerjee, SomeJoint), source 18d6760953783bec316ddb46266a1b5ccc50c291fbf47ec35f87c73f4d0cf2ac. build.py closure vendored verbatim under tasks/dqi/fused/source/. Design lineage: rebuilt from a pseudocode description of the Schur decoder (jday96314/QuantumAI, no licence; card aba6c540, D-PRA269-01, D-PRA273-01); recorded, not gated. See tasks/dqi/fused/PROVENANCE.md. No circuit input.')
        manifest = start_candidate(ZIP, CANDIDATE, provenance, parent_candidate_id=PARENT,
            salt_label=config.salt_label,
            notes=f'PRA-293: {PARENT} (#62) with only dqi.kmb changed to the vendored fused decoder. No salt/seed search or upload. Adjudicator review required before merge/submission.')
        for task in ('invsqrt', 'dfthcsos'):
            if manifest.tasks[task].files != parent.tasks[task].files:
                raise ValueError(f'{task} files differ from {PARENT}')
        if manifest.tasks['dqi'].files != {'dqi.kmb': FUSED_SHA256}:
            raise ValueError('dqi files are not the fused build alone')
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
