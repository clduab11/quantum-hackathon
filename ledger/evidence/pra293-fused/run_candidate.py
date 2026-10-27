"""Run PRA-293's exact bundle through G0–G5; resume uncleared gates on rerun.

Example: OPENBLAS_NUM_THREADS=1 PYTHONPATH=. uv run python
  ledger/evidence/pra293-fused/run_candidate.py --dry-run
The bundle is submission-008's (pra280-rustad) with only dqi.kmb replaced by
the tasks/dqi/generate_fused.py output; DATA/pra293-fused/bundle must hold it.
Writes a deterministic zip, candidate manifest, gate evidence and queue entry.
A mismatch or failed gate exits nonzero; no upload or service call occurs.
"""
import argparse
import json
from pathlib import Path
import time

from ledger.archive import build_zip
from ledger.gates.runner import load_config, run_pipeline, start_candidate
from ledger.run_manifest import Provenance, read_manifest, sha256_file, write_manifest

ROOT = Path(__file__).resolve().parents[3]
DATA = Path('/home/cld-main/work/vqcc-data')
CANDIDATE = 'pra293-fused'
PARENT = 'pra280-rustad'
BUNDLE = DATA / CANDIDATE / 'bundle'
ZIP = DATA / CANDIDATE / f'{CANDIDATE}.zip'
MANIFEST = ROOT / f'ledger/manifests/candidates/{CANDIDATE}.json'


def check_only_dqi_changed(parent):
    """The bundle must equal the parent's files except dqi.kmb."""
    files = {str(p.relative_to(BUNDLE)): sha256_file(p) for p in BUNDLE.rglob('*') if p.is_file()}
    expected = {rel: digest for record in parent.tasks.values() for rel, digest in record.files.items()}
    if set(files) != set(expected):
        raise ValueError(f'bundle members differ from {PARENT}: {sorted(set(files) ^ set(expected))}')
    changed = sorted(rel for rel in files if files[rel] != expected[rel])
    if changed != ['dqi.kmb']:
        raise ValueError(f'expected only dqi.kmb to change, got {changed}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Print paths; write nothing and run no gates.')
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({'bundle': str(BUNDLE), 'zip': str(ZIP), 'manifest': str(MANIFEST),
                          'parent': PARENT, 'gates': 'G0-G5; no waivers'}, indent=2))
        return
    config = load_config(ROOT / 'configs/gates/pra293-fused.yaml')
    parent = read_manifest(ROOT / f'ledger/manifests/candidates/{PARENT}.json')
    if MANIFEST.exists():
        manifest = read_manifest(MANIFEST)
    else:
        if ZIP.exists():
            raise FileExistsError('zip exists without manifest; inspect before retrying')
        check_only_dqi_changed(parent)
        build_zip(BUNDLE, ZIP)
        provenance = {task: record.provenance for task, record in parent.tasks.items()}
        provenance['dqi'] = Provenance(licence='Apache-2.0',
            parent_url='https://www.kaggle.com/code/somejoint/quantum-circuits-21-34-local-gm-fused-dqi',
            notes='Kernel 140675727 v12 (Agniv Banerjee, SomeJoint), source 18d6760953783bec316ddb46266a1b5ccc50c291fbf47ec35f87c73f4d0cf2ac. build.py closure vendored verbatim under tasks/dqi/fused/source/. Design lineage: rebuilt from a pseudocode description of the Schur decoder (jday96314/QuantumAI, no licence; card aba6c540, D-PRA269-01, D-PRA273-01); recorded, not gated. See tasks/dqi/fused/PROVENANCE.md. No circuit input.')
        manifest = start_candidate(ZIP, CANDIDATE, provenance,
            parent_candidate_id=PARENT, salt_label=config.salt_label,
            notes='PRA-293: submission-008 with only dqi.kmb changed to the vendored fused decoder. No salt/seed search, GPU work or upload. Adjudicator review required before merge/submission.')
        write_manifest(manifest, MANIFEST, exclusive=True)
    started = time.monotonic()
    records = run_pipeline(manifest, ZIP, config, manifest_file=MANIFEST, package_root=DATA)
    summary = dict(gates=[dict(gate=r.gate, status=r.status, reason=r.reason) for r in records],
                   seconds=time.monotonic()-started, shipping_problems=manifest.shipping_problems(),
                   geometric_mean=manifest.geometric_mean, zip_sha256=sha256_file(ZIP),
                   generator_commit=manifest.generator_commit)
    (Path(__file__).parent / 'pipeline.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2), flush=True)
    if manifest.shipping_problems():
        raise SystemExit(1)


if __name__ == '__main__':
    main()
