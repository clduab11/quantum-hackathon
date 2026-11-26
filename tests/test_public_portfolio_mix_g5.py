# SPDX-License-Identifier: Apache-2.0
"""The real G5 rebuild over the actual stager with a several-source toy pin (D-HERMES-20261113-01).

The stager source is copied byte for byte into the conftest fixture repository beside a toy pin
named on the command line with ``--pin``, as configs/gates/hermes-mix-20261113.yaml does. G0 to
G3 are the ledger fakes; G4 and G5 are the real checks. Only tiny toy bytes are staged.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

from conftest import git
from ledger.archive import build_zip
from ledger.gates.runner import GATE_IDS, load_config, run_pipeline, start_candidate
from ledger.run_manifest import Provenance
from tasks.public_portfolio import generate

REPO = Path(__file__).resolve().parents[1]
REAL_CONFIG = REPO / 'configs/gates/hermes-mix-20261113.yaml'
# SOURCE.json rides along unchanged: the stager reads the v12 default pin when it is imported.
STAGER_SOURCES = ('tasks/__init__.py', 'tasks/public_portfolio/__init__.py',
                  'tasks/public_portfolio/generate.py', 'tasks/public_portfolio/SOURCE.json')
PIN_NAME = 'MIX-20261113.json'  # the toy pin takes the real name, so the real argv is used
TASKS = ('invsqrt', 'dqi', 'dfthcsos')
DIRS = {'s1': 'inputs/fixture/one-v1', 's2': 'inputs/fixture/two-v2', 's3': 'inputs/fixture/three-v3'}
URL = 'https://example.invalid/{}'
RECORD = 'fixture-licence-record'
BLOBS = {
    ('s1', 'invsqrt.kmb'): b'toy mix invsqrt\n' * 3,
    ('s2', 'dqi.kmb'): b'toy mix dqi\n' * 5,
    ('s3', 'dfthcsos__angle_k_0.kmb'): b'toy mix angle zero\n' * 4,
    ('s3', 'dfthcsos__submission.npz'): b'toy mix factor, not a real npz\n' * 2,
}


def _task(name: str) -> str:
    return 'dfthcsos' if name.startswith('dfthcsos__') else name.removesuffix('.kmb')


def _sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _toy_pin() -> dict:
    return {
        'kind': 'vendored_circuit', 'licence_record': RECORD,
        'sources': {s: {'owner': s, 'version': '1', 'licence': 'Apache-2.0',
                        'source_url': URL.format(s), 'input_dir': d} for s, d in DIRS.items()},
        'files': [{'source': s, 'dataset_file': n, 'task': _task(n), 'output': n.replace('__', '/', 1),
                   'kind': 'vendored_circuit' if n.endswith('.kmb') else 'package_input',
                   'sha256': _sha(b), 'size_bytes': len(b)} for (s, n), b in BLOBS.items()],
    }


def _declared_inputs() -> dict:
    inputs: dict[str, list] = {t: [] for t in TASKS}
    for (source, name), blob in BLOBS.items():
        entry = {'path': f'{DIRS[source]}/{name}', 'sha256': _sha(blob)}
        if name.endswith('.kmb'):
            entry = {'kind': 'vendored_circuit', **entry, 'source_url': URL.format(source),
                     'version': '1', 'licence': 'Apache-2.0', 'licence_record': RECORD}
        inputs[_task(name)].append(entry)
    return inputs


@pytest.fixture
def mixed(workspace):
    for rel in STAGER_SOURCES:
        dest = workspace.repo / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, dest)
    toy = f'tasks/public_portfolio/{PIN_NAME}'
    (workspace.repo / toy).write_bytes((json.dumps(_toy_pin(), indent=2) + '\n').encode())
    git(workspace.repo, 'add', *STAGER_SOURCES, toy)
    git(workspace.repo, 'commit', '-q', '-m', 'actual stager, toy several-source pin')
    for (source, name), blob in BLOBS.items():
        folder = workspace.package_root / DIRS[source]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(blob)
    real = yaml.safe_load(REAL_CONFIG.read_text(encoding='utf-8'))
    raw = yaml.safe_load(workspace.config.path.read_text())
    raw['generators'] = real['generators']
    raw['inputs'] = _declared_inputs()
    path = workspace.root / 'mix-gates.yaml'
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return load_config(path)


def test_toy_declarations_have_the_real_mix_shape():
    generate.validate_pin(_toy_pin())
    real = yaml.safe_load(REAL_CONFIG.read_text(encoding='utf-8'))
    assert {frozenset(e) for v in real['inputs'].values() for e in v} == {
        frozenset(e) for v in _declared_inputs().values() for e in v}


def test_real_g5_rebuilds_a_several_source_mix_byte_for_byte(workspace, fakes, mixed):
    built = workspace.root / 'built-mix'
    env = {**os.environ, 'VQCC_DATA': str(workspace.package_root), 'PYTHONDONTWRITEBYTECODE': '1'}
    for task in TASKS:
        argv = [a.format(python=sys.executable, out=str(built), worktree=str(workspace.repo))
                for a in mixed.generators[task]]
        done = subprocess.run(argv, cwd=workspace.repo, capture_output=True, text=True, env=env,
                              check=False)
        assert done.returncode == 0, done.stderr
    zip_path = build_zip(built, workspace.root / 'mix-ok.zip')
    provenance = {t: Provenance(licence='Apache-2.0', parent_url=URL.format('s1')) for t in TASKS}
    manifest = start_candidate(zip_path, 'mix-ok', provenance, salt_label=mixed.salt_label,
                               repo=workspace.repo)
    assert manifest.generator_commit == git(workspace.repo, 'rev-parse', 'HEAD')
    records = run_pipeline(manifest, zip_path, mixed, queue_dir=workspace.queue_dir,
                           **workspace.context())
    assert [(r.gate, r.status) for r in records] == [(g, 'PASS') for g in GATE_IDS], records
    with zipfile.ZipFile(zip_path) as archive:
        assert sorted(archive.namelist()) == sorted(n.replace('__', '/', 1) for _, n in BLOBS)
    rebuild = manifest.latest_gate('G5').details['rebuild']
    assert rebuild['vendored_circuits'] == {
        n.replace('__', '/', 1): f'{DIRS[s]}/{n}' for s, n in BLOBS if n.endswith('.kmb')}
    assert rebuild['copied_inputs'] == {
        'dfthcsos/submission.npz': f"{DIRS['s3']}/dfthcsos__submission.npz"}
    assert manifest.shipping_problems() == []
