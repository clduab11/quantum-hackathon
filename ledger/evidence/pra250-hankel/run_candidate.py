"""Run the exact PRA-250 bundle through real gates; no waivers or uploads.

Run from the repo root with PYTHONPATH=. and the documented local environment.
The zip must already be built from the three committed generators.
"""
from pathlib import Path
import json
import time

from ledger.gates.runner import load_config, run_pipeline, start_candidate
from ledger.run_manifest import Provenance, read_manifest, write_manifest

REPO = Path(__file__).resolve().parents[3]
CANDIDATE = 'pra250-hankel'
ZIP = Path('/home/cld-main/work/vqcc-data/queue/pra250-hankel.zip')
MANIFEST = REPO / f'ledger/manifests/candidates/{CANDIDATE}.json'
CONFIG = REPO / 'configs/gates/pra250-hankel.yaml'


def main():
    parent = read_manifest(REPO / 'ledger/manifests/candidates/pra233-2-dqi-q881.json')
    shipped = read_manifest(REPO / 'ledger/manifests/submissions/submission-004.json')
    assert parent.zip_sha256 == shipped.zip_sha256
    if MANIFEST.exists():
        manifest = read_manifest(MANIFEST)
    else:
        provenance = {name: task.provenance for name, task in parent.tasks.items()}
        provenance['dqi'] = Provenance(
            licence='Apache-2.0',
            parent_url='https://www.kaggle.com/code/somejoint/quantum-circuits-13-54-local-gm-cost-gains',
            notes='Kernel 140675727 v7, cell-34 Apache grant. Hankel/cyclic Gold port; inherited audited jfraction arithmetic and independent Praxen projection. See tasks/dqi/hankel/PROVENANCE.md. No circuit input.')
        provenance['dfthcsos'] = Provenance(
            licence='Apache-2.0',
            parent_url='https://www.kaggle.com/datasets/dmitriigluzdov/vqcc-femoco-public-factorization?datasetVersionNumber=8',
            notes='PRA-245 declared Gluzdov v8 non-circuit factor, SHA 809a992900937425f01a0593803921873f7bb472d590592c378d3ceb23657df5. Committed ANF builder, J10, 11-bit words; PRA-247 family. All ANGLE circuits regenerated.')
        manifest = start_candidate(ZIP, CANDIDATE, provenance,
            parent_candidate_id=parent.candidate_id,
            salt_label='PRA171_LOCAL_PUBLIC_FIXED_SALT_0001', repo=REPO,
            notes='PRA-250 fixed Hankel source port; no Phuc wrapper output or seed/salt selection. Local generator commit pending governed publication; not upload approval.')
        write_manifest(manifest, MANIFEST, exclusive=True)
    config = load_config(CONFIG)
    start = time.monotonic()
    context = dict(repo=REPO, package_root=Path('/home/cld-main/work/vqcc-data'))
    records = run_pipeline(manifest, ZIP, config, stop_after='G3', manifest_file=MANIFEST, **context)
    for record in records:
        print(record.gate, record.status, record.reason, flush=True)
    if not manifest.gate_cleared('G3'):
        raise RuntimeError('Full verification did not pass')
    dqi = manifest.tasks['dqi']
    assert dqi.ratio >= 25 and dqi.metrics['value_errors'] == 0
    # Phase-error comparison needs the public build's matching-salt report.
    # Preserve the measured count; do not invent that missing baseline.
    assert manifest.tasks['dfthcsos'].ratio >= 3.8
    records = run_pipeline(manifest, ZIP, config, manifest_file=MANIFEST, **context)
    for record in records:
        print(record.gate, record.status, record.reason, flush=True)
    print(json.dumps({'shipping_problems': manifest.shipping_problems(),
                      'geometric_mean': manifest.geometric_mean,
                      'seconds': time.monotonic()-start}, indent=2), flush=True)
    if manifest.shipping_problems():
        raise RuntimeError('Candidate is not shipping-ready')


if __name__ == '__main__':
    main()
