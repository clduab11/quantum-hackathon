# SPDX-License-Identifier: Apache-2.0
"""The real G5 rebuild path over the actual tasks.public_portfolio stager (D-HERMES-20261112-02,
D-PRA341-01).

Compatibility coverage. The unchanged stager source (tasks/__init__.py,
tasks/public_portfolio/__init__.py, tasks/public_portfolio/generate.py) is copied byte for byte
into the conftest fixture repository beside a toy SOURCE.json and committed there. The generator
argv is taken verbatim from configs/gates/hermes-syed-v12.yaml. G0 to G3 are the ledger fakes;
G4 and G5 are the real checks. The pins are tiny toy bytes: no real circuit is read, staged,
hashed, loaded or verified. The circuits are vendored pins, not circuits we generated.
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
REAL_CONFIG = REPO / 'configs/gates/hermes-syed-v12.yaml'
STAGER_SOURCES = ('tasks/__init__.py', 'tasks/public_portfolio/__init__.py',
                  'tasks/public_portfolio/generate.py')
TOY_SOURCE = 'tasks/public_portfolio/SOURCE.json'
TASKS = ('invsqrt', 'dqi', 'dfthcsos')
INPUT_DIR = 'inputs/fixture/toy-portfolio-v1'
SOURCE_URL = 'https://example.invalid/datasets/toy-portfolio/versions/1'
VERSION = '1'
LICENCE_RECORD = 'fixture-licence-record'  # toy ticket id; the real record is provenance.md
BLOBS = {
    'invsqrt.kmb': b'toy invsqrt circuit bytes\n' * 3,
    'dqi.kmb': b'toy dqi circuit bytes\n' * 5,
    'dfthcsos__angle_k_0.kmb': b'toy dfthcsos angle zero\n' * 4,
    'dfthcsos__submission.npz': b'toy factor archive, not a real npz\n' * 2,
}
TAMPERED = b'Z' * len(BLOBS['dfthcsos__angle_k_0.kmb'])
NO_DIFFS = {'missing': [], 'extra': [], 'changed': []}


def _task_of(name: str) -> str:
    return 'dfthcsos' if name.startswith('dfthcsos__') else name.removesuffix('.kmb')


def _output_of(name: str) -> str:
    return name.replace('__', '/', 1)


def _sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _toy_pin() -> dict:
    files = [{'dataset_file': name, 'task': _task_of(name), 'output': _output_of(name),
              'kind': 'vendored_circuit' if name.endswith('.kmb') else 'package_input',
              'sha256': _sha(blob), 'size_bytes': len(blob)} for name, blob in BLOBS.items()]
    return {'kind': 'vendored_circuit', 'owner': 'fixture', 'version': VERSION,
            'source_url': SOURCE_URL, 'input_dir': INPUT_DIR, 'licence': 'Apache-2.0',
            'licence_record': LICENCE_RECORD, 'files': files}


def _declared_inputs() -> dict[str, list[dict[str, str]]]:
    inputs: dict[str, list[dict[str, str]]] = {t: [] for t in TASKS}
    for name, blob in BLOBS.items():
        entry = {'path': f'{INPUT_DIR}/{name}', 'sha256': _sha(blob)}
        if name.endswith('.kmb'):
            entry = {'kind': 'vendored_circuit', **entry, 'source_url': SOURCE_URL,
                     'version': VERSION, 'licence': 'Apache-2.0',
                     'licence_record': LICENCE_RECORD}
        inputs[_task_of(name)].append(entry)
    return inputs


def _write_blobs(root: Path) -> None:
    folder = root / INPUT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    for name, blob in BLOBS.items():
        (folder / name).write_bytes(blob)


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob('*')) if p.is_file()}


@pytest.fixture
def portfolio(workspace):
    """Commit the actual stager with a toy SOURCE.json in the fixture repo, put the toy pinned
    files in the fake package, and return a gate config with the real hermes-syed-v12
    generator argv, the toy declared inputs, fake G0-G3 and the real G4/G5."""
    for rel in STAGER_SOURCES:
        dest = workspace.repo / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, dest)
        assert dest.read_bytes() == (REPO / rel).read_bytes()
    pin = _toy_pin()
    generate.validate_pin(pin)
    (workspace.repo / TOY_SOURCE).write_bytes((json.dumps(pin, indent=2) + '\n').encode())
    git(workspace.repo, 'add', *STAGER_SOURCES, TOY_SOURCE)
    git(workspace.repo, 'commit', '-q', '-m', 'actual public-portfolio stager, toy pins')
    _write_blobs(workspace.package_root)

    real = yaml.safe_load(REAL_CONFIG.read_text(encoding='utf-8'))
    raw = yaml.safe_load(workspace.config.path.read_text())
    raw['generators'] = real['generators']
    raw['inputs'] = _declared_inputs()
    path = workspace.root / 'portfolio-gates.yaml'
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return load_config(path)


def _stage_cli(workspace, config, task: str, out: Path) -> subprocess.CompletedProcess:
    """Run the fixture copy of the stager with the configured argv, as G5 does."""
    argv = [a.format(python=sys.executable, out=str(out), worktree=str(workspace.repo))
            for a in config.generators[task]]
    env = {**os.environ, 'VQCC_DATA': str(workspace.package_root),
           'PYTHONDONTWRITEBYTECODE': '1'}  # keep the fixture repo clean for generator_commit
    return subprocess.run(argv, cwd=workspace.repo, capture_output=True, text=True, env=env,
                          check=False)


def _build(workspace, config, name: str) -> Path:
    built = workspace.root / name
    for task in TASKS:
        done = _stage_cli(workspace, config, task, built)
        assert done.returncode == 0, done.stderr
        assert json.loads(done.stdout)['task'] == task
    return built


def _gate(workspace, config, built: Path, candidate_id: str):
    zip_path = build_zip(built, workspace.root / f'{candidate_id}.zip')
    provenance = {t: Provenance(licence='Apache-2.0', parent_url=SOURCE_URL) for t in TASKS}
    manifest = start_candidate(zip_path, candidate_id, provenance,
                               salt_label=config.salt_label, repo=workspace.repo)
    assert manifest.generator_commit == git(workspace.repo, 'rev-parse', 'HEAD')  # not -dirty
    records = run_pipeline(manifest, zip_path, config, queue_dir=workspace.queue_dir,
                           **workspace.context())
    return zip_path, manifest, records


def test_toy_declarations_have_the_real_hermes_syed_v12_shape():
    generate.validate_pin(_toy_pin())
    real = yaml.safe_load(REAL_CONFIG.read_text(encoding='utf-8'))
    real_shapes = {frozenset(e) for entries in real['inputs'].values() for e in entries}
    toy_shapes = {frozenset(e) for entries in _declared_inputs().values() for e in entries}
    assert toy_shapes == real_shapes  # one vendored_circuit shape, one plain npz shape
    for task in TASKS:
        assert real['generators'][task] == [
            '{python}', '-m', 'tasks.public_portfolio.generate', '--task', task, '--out', '{out}']


def test_real_g5_rebuilds_the_actual_stager_output_byte_for_byte(workspace, fakes, portfolio):
    built = _build(workspace, portfolio, 'built-portfolio')
    pinned = {_output_of(n): _sha(b) for n, b in BLOBS.items()}
    zip_path, manifest, records = _gate(workspace, portfolio, built, 'portfolio-ok')

    assert [(r.gate, r.status) for r in records] == [(g, 'PASS') for g in GATE_IDS], records
    assert set(fakes.CALLS) == {'g0', 'g1', 'g2', 'g3'}  # fake G0-G3 only, no real hook
    with zipfile.ZipFile(zip_path) as archive:
        assert sorted(archive.namelist()) == sorted(pinned)  # no .partial, nothing extra
    shipped = {rel: digest for t in TASKS for rel, digest in manifest.tasks[t].files.items()}
    assert shipped == pinned

    rebuild = manifest.latest_gate('G5').details['rebuild']
    assert rebuild['status'] == 'PASS' and rebuild['commit'] == manifest.generator_commit
    for task in TASKS:
        record = rebuild['tasks'][task]
        assert record['identical'] is True and record['returncode'] == 0, record
        assert record['diffs'] == NO_DIFFS
        assert record['argv'][0] == sys.executable
        assert record['argv'][1:-1] == [
            '-m', 'tasks.public_portfolio.generate', '--task', task, '--out']
        # Every rebuilt file is a byte copy of its own pin, and nothing else was rebuilt.
        assert record['copied'] == {_output_of(n): f'{INPUT_DIR}/{n}'
                                    for n in BLOBS if _task_of(n) == task}
    assert rebuild['vendored_circuits'] == {
        _output_of(n): f'{INPUT_DIR}/{n}' for n in BLOBS if n.endswith('.kmb')}
    assert rebuild['copied_inputs'] == {
        'dfthcsos/submission.npz': f'{INPUT_DIR}/dfthcsos__submission.npz'}
    assert rebuild['inputs'] == {_sha(b): f'{INPUT_DIR}/{n}' for n, b in BLOBS.items()}
    assert manifest.shipping_problems() == []
    assert (workspace.queue_dir / 'portfolio-ok.zip').exists()


def test_a_retained_partial_cannot_ride_along_in_a_later_successful_build(
        workspace, fakes, portfolio, monkeypatch):
    # An earlier dfthcsos run fails mid-copy: the stager keeps its .partial and deletes nothing.
    failed_data = workspace.root / 'failed-data'
    _write_blobs(failed_data)
    victim = failed_data / INPUT_DIR / 'dfthcsos__angle_k_0.kmb'
    real_preflight = generate.preflight

    def change_after_preflight(*args, **kwargs):
        plan = real_preflight(*args, **kwargs)
        victim.write_bytes(TAMPERED)
        return plan

    failed_out = workspace.root / 'failed-out'
    with monkeypatch.context() as patch:
        patch.setattr(generate, 'preflight', change_after_preflight)
        with pytest.raises(ValueError, match='input changed while copying'):
            generate.stage('dfthcsos', failed_data, failed_out, pin=_toy_pin())
    retained = failed_out / 'dfthcsos' / 'angle_k_0.kmb.partial'
    assert _tree(failed_out) == {'dfthcsos/angle_k_0.kmb.partial': TAMPERED}

    # The committed stager refuses to retry into the kept output, so it never mixes by itself.
    retry = _stage_cli(workspace, portfolio, 'dfthcsos', failed_out)
    assert retry.returncode == 1 and 'refusing' in retry.stderr, retry.stderr
    assert _tree(failed_out) == {'dfthcsos/angle_k_0.kmb.partial': TAMPERED}

    # A later run into a fresh directory succeeds; a hand merge then carries the kept file along.
    built = _build(workspace, portfolio, 'built-mixed')
    assert not list(built.rglob('*.partial'))
    shutil.copyfile(retained, built / 'dfthcsos' / retained.name)
    _, manifest, records = _gate(workspace, portfolio, built, 'portfolio-mixed')

    assert [(r.gate, r.status) for r in records] == (
        [(g, 'PASS') for g in GATE_IDS[:-1]] + [('G5', 'FAIL')]), records
    assert 'rebuild differs for dfthcsos' in records[-1].reason
    rebuild = manifest.latest_gate('G5').details['rebuild']
    assert rebuild['tasks']['dfthcsos']['diffs'] == {
        'missing': ['dfthcsos/angle_k_0.kmb.partial'], 'extra': [], 'changed': []}
    assert rebuild['tasks']['invsqrt']['identical'] is True
    assert rebuild['tasks']['dqi']['identical'] is True
    assert manifest.shipping_problems()
    assert not (workspace.queue_dir / 'portfolio-mixed.zip').exists()
    assert retained.read_bytes() == TAMPERED  # soft-delete only: the failed artifact is kept
