"""Run PRA-280's exact bundle through G0–G5; resume uncleared gates on rerun.

Example: OPENBLAS_NUM_THREADS=1 PYTHONPATH=. uv run python
  ledger/evidence/pra280-rustad/run_candidate.py --dry-run
Requires the three generated files/family under DATA/pra280/bundle, the pinned
factor under DATA/inputs/rustad, and the standard organizer environment.
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
CANDIDATE = 'pra280-rustad'
ZIP = DATA / 'pra280' / f'{CANDIDATE}.zip'
MANIFEST = ROOT / f'ledger/manifests/candidates/{CANDIDATE}.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Print paths; write nothing and run no gates.')
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({'bundle': str(DATA / 'pra280/bundle'), 'zip': str(ZIP),
                          'manifest': str(MANIFEST), 'gates': 'G0-G5; no waivers'}, indent=2))
        return
    config = load_config(ROOT / 'configs/gates/pra280-rustad.yaml')
    if MANIFEST.exists():
        manifest = read_manifest(MANIFEST)
    else:
        if ZIP.exists():
            raise FileExistsError('zip exists without manifest; inspect before retrying')
        build_zip(DATA / 'pra280/bundle', ZIP)
        parent = read_manifest(ROOT / 'ledger/manifests/candidates/pra250-hankel.json')
        provenance = {task: record.provenance for task, record in parent.tasks.items()}
        provenance['dqi'] = Provenance(licence='not-stated',
            parent_url='https://github.com/jday96314/QuantumAI',
            notes='Existing committed Schur generator; upstream 2b922709. See tasks/dqi/schur/PROVENANCE.md. Licence recorded, not gated under PRA-273. No circuit input.')
        provenance['dfthcsos'] = Provenance(licence='Other (specified in description)',
            parent_url='https://www.kaggle.com/datasets/michaelrustad/vqcc-dfthc-r10-merged-groups?datasetVersionNumber=1',
            notes='Declared non-circuit factor SHA-256 27dda66f38c60821665cfc74e51d1bd2bfd2a7f0d902dbaffcdc5b26543dadad, copied under D-PRA211-05. All circuits regenerated with the mrmeows v6 source port (Apache 2.0), exact integer gauge, J3/brot8. Full source rows: ledger/manifests/inputs/pra280-rustad.json; notices/35-chem-catchup.txt.')
        manifest = start_candidate(ZIP, CANDIDATE, provenance,
            parent_candidate_id=parent.candidate_id, salt_label=config.salt_label,
            notes='PRA-280 public parity candidate. No salt/seed search, GPU work or upload. Adjudicator review required before merge/submission.')
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
