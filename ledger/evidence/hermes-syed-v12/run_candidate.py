"""Run the G0-G5 chain on the exact hermes-syed-v12 candidate zip (D-HERMES-20261112-02).

Usage, from a checkout whose candidate paths are committed:

    uv run python ledger/evidence/hermes-syed-v12/run_candidate.py [--stop-after G2]

The zip is pinned by SHA-256 below; any other bytes are refused before a manifest is written.
The manifest records the committed generator revision, and G5 rebuilds that revision in a clean
worktree. A pre-existing manifest is resumed: gates already PASS on this zip are skipped.
This script never reserves a slot and never uploads.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CANDIDATE_ID = 'hermes-syed-v12'
PARENT_ID = 'pra325-invsqrt-vendored-63q'
CONFIG = ROOT / 'configs/gates/hermes-syed-v12.yaml'
SOURCE = ROOT / 'tasks/public_portfolio/SOURCE.json'
ZIP_SHA256 = '55ee2315fddb8622401fe616e6bcebacf9cffc87ce8c064dadc9d990dec2528c'
ZIP_SIZE = 49_305_565
DEFAULT_ZIP = Path(os.environ.get(
    'HERMES_SYED_V12_ZIP',
    'C:/Users/cld-main/Desktop/ops/quantum-hackathon-phase0-data/public-base-v12/'
    'hermes-syed-v12-windows-20261112.zip'))
DEFAULT_PACKAGE_ROOT = Path(os.environ.get(
    'HERMES_SYED_V12_PACKAGE_ROOT', 'C:/Users/cld-main/Desktop/ops/quantum-hackathon-phase0-data'))
# A candidate is only as committed as these paths; G5 rebuilds them at the recorded revision.
CANDIDATE_PATHS = (
    '.gitattributes',
    'tasks/public_portfolio',
    'configs/gates/hermes-syed-v12.yaml',
    'ledger/evidence/hermes-syed-v12/run_candidate.py',
    'ledger/evidence/hermes-syed-v12/provenance.md',
    'notices/50-public-portfolio.txt',
    'docs/decisions/D-HERMES-20261112-01.md',
    'docs/decisions/D-HERMES-20261112-02.md',
    'ledger/benchmark_health.py',
    'ledger/gates',
    'ledger/run_manifest.py',
    'ledger/archive.py',
    'harness',
)
NOTES = ('Apache-2.0 vendored circuits, pinned by URL, version and SHA-256; the author\'s '
         'own-work and no-public-code statements are recorded, not certified by this repository.')


def pinned_files() -> dict[str, dict[str, str]]:
    """Expected per-task archive members and SHA-256s, from the committed pin."""
    pin = json.loads(SOURCE.read_text(encoding='utf-8'))
    expected: dict[str, dict[str, str]] = {}
    for entry in pin['files']:
        output = entry['output']
        task = entry['task']
        name = output if task == 'dfthcsos' else output.split('/')[-1]
        expected.setdefault(task, {})[name] = entry['sha256']
    return expected


def provenance():
    from ledger.run_manifest import Provenance

    pin = json.loads(SOURCE.read_text(encoding='utf-8'))
    return {
        task: Provenance(licence=pin['licence'], parent_url=pin['source_url'], notes=NOTES)
        for task in ('invsqrt', 'dqi', 'dfthcsos')
    }


def check_zip(path: Path) -> Path:
    from ledger.run_manifest import sha256_file

    path = Path(path)
    if not path.is_file():
        raise ValueError(f'{path} is missing; expected the built candidate zip')
    size, digest = path.stat().st_size, sha256_file(path)
    if size != ZIP_SIZE or digest != ZIP_SHA256:
        raise ValueError(f'{path} is {size} bytes, SHA-256 {digest[:12]}; '
                         f'expected the built candidate {ZIP_SHA256[:12]} ({ZIP_SIZE} bytes)')
    return path


def check_committed() -> str:
    """Refuse dirty candidate paths, then return HEAD (the revision G5 rebuilds)."""
    dirty = subprocess.check_output(
        ['git', 'status', '--porcelain', '--', *CANDIDATE_PATHS], cwd=ROOT, text=True)
    if dirty.strip():
        raise ValueError('commit the candidate paths before gating; dirty:\n' + dirty)
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


def check_pins(manifest) -> None:
    expected = pinned_files()
    for task, files in expected.items():
        if dict(manifest.tasks[task].files) != files:
            raise ValueError(f'{task}: zip members differ from tasks/public_portfolio/SOURCE.json')


def main(argv=None) -> int:
    from ledger.gates.runner import load_config, run_pipeline, start_candidate
    from ledger.run_manifest import (MANIFESTS_DIR, ManifestError, manifest_path, read_manifest,
                                     write_manifest)

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--zip', type=Path, default=DEFAULT_ZIP)
    parser.add_argument('--package-root', type=Path, default=DEFAULT_PACKAGE_ROOT,
                        help='root holding the declared inputs G5 stages (inputs/syed3000/...)')
    parser.add_argument('--stop-after', default=None)
    args = parser.parse_args(argv)
    try:
        zip_path = check_zip(args.zip)
        head = check_committed()
        path = MANIFESTS_DIR / 'candidates' / f'{CANDIDATE_ID}.json'
        if path.exists():
            manifest = read_manifest(path)
            if manifest.zip_sha256 != ZIP_SHA256:
                raise ValueError(f'{path} records another zip; refusing to mix evidence')
        else:
            manifest = start_candidate(zip_path, CANDIDATE_ID, provenance(),
                                       parent_candidate_id=PARENT_ID, notes=NOTES)
            if manifest.generator_commit != head:
                raise ValueError(f'manifest recorded {manifest.generator_commit}, HEAD is {head}')
            check_pins(manifest)
            path = write_manifest(manifest, manifest_path(manifest), exclusive=True)
        check_pins(manifest)
        records = run_pipeline(manifest, zip_path, load_config(CONFIG), stop_after=args.stop_after,
                               manifest_file=path, package_root=args.package_root)
    except (ManifestError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'REFUSED: {exc}', file=sys.stderr)
        return 1
    for record in records:
        print(f'{record.gate} {record.status} {record.summary if hasattr(record, "summary") else ""}')
    final = read_manifest(path)
    statuses = {g.gate: g.status for g in final.gates}
    print(json.dumps({'manifest': str(path), 'gates': statuses,
                      'geometric_mean': final.geometric_mean,
                      'shipping_problems': final.shipping_problems()}, indent=1))
    return 0 if all(statuses.get(g) == 'PASS' for g in ('G0', 'G1', 'G2', 'G3', 'G4', 'G5')) \
        and not final.shipping_problems() else 1


if __name__ == '__main__':
    raise SystemExit(main())
