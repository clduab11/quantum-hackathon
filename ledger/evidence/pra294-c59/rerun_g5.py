"""Re-run G5 alone on PRA-294's recorded manifest at the same generator commit (D-PRA294-01).

Example: TMPDIR=/home/cld-main/work/vqcc-data/pra294-c59/tmp OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 UV_NO_SYNC=1 PYTHONPATH=. uv run python ledger/evidence/pra294-c59/rerun_g5.py
The first G5 record failed because the agent run that started the pipeline ended and its scratch
directory (the extracted zip) was deleted under it. This uses ledger.gates.runner.rerun_gate with
the same repo and package root as run_candidate.py; the FAIL stays in the manifest as history and
no G0-G4 record, zip, seed or circuit changes.
"""
import json
from pathlib import Path

from ledger.gates.runner import load_config, rerun_gate
from ledger.run_manifest import read_manifest
import run_candidate as rc  # sibling script (sys.path[0]); paths only

HERE = Path(__file__).parent

NOTE = ('D-PRA294-01: G5 re-run at the same generator commit after the first G5 record failed on a '
        'deleted scratch directory (environment, not the zip).')


def main():
    manifest = read_manifest(rc.MANIFEST)
    record = rerun_gate(manifest, 'G5', rc.ZIP, load_config(rc.CONFIG),
                        generator_commit=manifest.generator_commit, note=NOTE,
                        manifest_file=rc.MANIFEST, repo=rc.ROOT, package_root=rc.DATA)
    summary = dict(gate=record.gate, status=record.status, reason=record.reason,
                   shipping_problems=manifest.shipping_problems(),
                   geometric_mean=manifest.geometric_mean, zip_sha256=manifest.zip_sha256,
                   generator_commit=manifest.generator_commit)
    (HERE / 'rerun-g5.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2), flush=True)
    if manifest.shipping_problems():
        raise SystemExit(1)


if __name__ == '__main__':
    main()
