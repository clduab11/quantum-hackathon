# SPDX-License-Identifier: Apache-2.0
"""Regression tests for the syed3000 v12 public-portfolio staging path (D-HERMES-20261112-02).

Everything here uses tiny fixture files. No real circuit is loaded, hashed or verified.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import yaml

from ledger.gates.runner import load_config
from ledger.run_manifest import vendored_circuit_licence_problems
from tasks.public_portfolio import gates, generate

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / 'configs/gates/hermes-syed-v12.yaml'
PROVENANCE = REPO / 'ledger/evidence/hermes-syed-v12/provenance.md'
NOTICE = REPO / 'notices/50-public-portfolio.txt'
DATASET_SUMS = Path(r'C:/Users/cld-main/Desktop/ops/quantum-hackathon-phase0-data/'
                    r'public-frontier/dataset/extracted/SHA256SUMS')

# Exact pins, transcribed from the dataset's SHA256SUMS (23 entries, all verified by the parent).
EXPECTED = {
    'invsqrt.kmb': '321aff83636214196daa9cbc9dcc9c5e12a155bcff8d9989e98b8cee40935177',
    'dqi.kmb': '7cbe8ecf6f6e9743529b574f019504bb1712ce06fbb570c719ce9d9e2c914cd9',
    'dfthcsos__angle_k_0.kmb': 'ce7ebaf342c5b49f7d539637359fb8a282718fb3057e7b25dd193f2a6a4b8974',
    'dfthcsos__angle_k_1.kmb': '3eac70665f021b0e304106fd62749277d4d69db775df008aacd6d950e4934193',
    'dfthcsos__angle_k_2.kmb': 'c3e1454e29a05c3c28bcfd16c2aee02340b5d439d9466774424fedf0ed7601d1',
    'dfthcsos__angle_k_3.kmb': 'd26b576ae789b0471ec6c11b7317c7c69eb3d7190472af8120ccf25cf217a8ea',
    'dfthcsos__angle_k_4.kmb': '2efacc9d944aa5a855acf780e6bbc3c07af16c0275eb9549bb24adc70acca344',
    'dfthcsos__angle_k_5.kmb': '7e4ed9a363c8f56d85410185c7b4449211788bc61e81b3dc7cbdd10ab7ce8a42',
    'dfthcsos__angle_k_6.kmb': '26ab1d5df8132bbc28e068a4eef0b247ea21a96fa4034f89a6d1bf306f07e284',
    'dfthcsos__angle_k_7.kmb': '1ae98642315e7aaedfde99773af4ae48198bf8b4f2e11e97883d6aa1bfe12bee',
    'dfthcsos__angle_k_8.kmb': 'e69c554c360c709e52126a6f773afeaa3564da7be0927d6293665f342203771f',
    'dfthcsos__angle_k_9.kmb': '38848ce19bd553e4007a454d9b7d392d05ac105cf4b269f41521bd1003bf838e',
    'dfthcsos__angle_k_10.kmb': 'fdb67807154e35d9f41471c22b38bbc3ed07e5c93efef30a57f0599fb8400ff7',
    'dfthcsos__angle_k_11.kmb': 'd22baf8e2d294165618bcee40d958ef2806f0b35352c8b92e0d201aff3269c37',
    'dfthcsos__angle_k_12.kmb': 'b1b6af502f4bf02e521ab888600f645aa5a5bed028290466b54a835423eb2517',
    'dfthcsos__angle_k_13.kmb': '1843d7993215656e4e0eee69169966ba269d544bc0b90e855e4ed5e6e113accc',
    'dfthcsos__angle_k_14.kmb': 'b763f0cd2fdeaaa31e7811084e51fde5d51575b036fa22854fb28172c1712a8e',
    'dfthcsos__submission.npz': '6418ec8e10b1a8da967ee26278434f9ac950474741185f4d61363e17a03da77f',
}
LICENCE_SHA256 = 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30'
README_SHA256 = 'f705cd243e22775f128ac4761cd3c3a49b8ae0400ef416f765964bc282635c6e'
INPUT_DIR = 'inputs/syed3000/vqcc-own-circuit-portfolio-v12'
SOURCE_URL = 'https://www.kaggle.com/datasets/syed3000/vqcc-own-circuit-portfolio/versions/12'

BLOBS = {
    'invsqrt.kmb': b'fixture invsqrt circuit',
    'dqi.kmb': b'fixture dqi circuit ' * 3,
    'dfthcsos__angle_k_0.kmb': b'fixture angle zero',
    'dfthcsos__angle_k_1.kmb': b'fixture angle one!!',
    'dfthcsos__submission.npz': b'fixture factor archive',
}


def _output_of(name: str) -> str:
    return name.replace('__', '/', 1)


def _fixture_pin() -> dict:
    files = []
    for name, blob in BLOBS.items():
        task = 'dfthcsos' if name.startswith('dfthcsos__') else name.removesuffix('.kmb')
        files.append({
            'dataset_file': name, 'task': task, 'output': _output_of(name),
            'kind': 'vendored_circuit' if name.endswith('.kmb') else 'package_input',
            'sha256': hashlib.sha256(blob).hexdigest(), 'size_bytes': len(blob),
        })
    return {'kind': 'vendored_circuit', 'owner': 'syed3000', 'version': '12',
            'input_dir': INPUT_DIR, 'files': files}


@pytest.fixture
def data(tmp_path):
    root = tmp_path / 'data'
    folder = root / INPUT_DIR
    folder.mkdir(parents=True)
    for name, blob in BLOBS.items():
        (folder / name).write_bytes(blob)
    return root


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob('*')) if p.is_file()}


# --- staging: happy paths ------------------------------------------------------------------


def test_stage_invsqrt_writes_only_the_pinned_leaf(data, tmp_path):
    out = tmp_path / 'out'
    report = generate.stage('invsqrt', data, out, pin=_fixture_pin())
    assert _tree(out) == {'invsqrt.kmb': BLOBS['invsqrt.kmb']}
    assert report['task'] == 'invsqrt'
    assert report['files'] == [{'output': 'invsqrt.kmb',
                                'sha256': hashlib.sha256(BLOBS['invsqrt.kmb']).hexdigest(),
                                'size_bytes': len(BLOBS['invsqrt.kmb'])}]


def test_stage_dqi_writes_only_the_dqi_leaf(data, tmp_path):
    out = tmp_path / 'out'
    generate.stage('dqi', data, out, pin=_fixture_pin())
    assert _tree(out) == {'dqi.kmb': BLOBS['dqi.kmb']}


def test_stage_dfthcsos_maps_double_underscore_to_directory(data, tmp_path):
    out = tmp_path / 'out'
    generate.stage('dfthcsos', data, out, pin=_fixture_pin())
    assert _tree(out) == {
        'dfthcsos/angle_k_0.kmb': BLOBS['dfthcsos__angle_k_0.kmb'],
        'dfthcsos/angle_k_1.kmb': BLOBS['dfthcsos__angle_k_1.kmb'],
        'dfthcsos/submission.npz': BLOBS['dfthcsos__submission.npz'],
    }


def test_stage_needs_only_the_requested_tasks_inputs(data, tmp_path):
    (data / INPUT_DIR / 'dqi.kmb').unlink()
    generate.stage('invsqrt', data, tmp_path / 'out', pin=_fixture_pin())
    assert (tmp_path / 'out/invsqrt.kmb').is_file()


def test_stage_streams_in_chunks_and_never_slurps(data, tmp_path, monkeypatch):
    monkeypatch.setattr(generate, 'CHUNK', 4)

    def boom(self):
        raise AssertionError('read_bytes would load a whole circuit into memory')
    monkeypatch.setattr(Path, 'read_bytes', boom)
    generate.stage('dqi', data, tmp_path / 'out', pin=_fixture_pin())
    monkeypatch.undo()
    assert (tmp_path / 'out/dqi.kmb').read_bytes() == BLOBS['dqi.kmb']


# --- staging: all pins checked before any write --------------------------------------------


@pytest.mark.parametrize('victim', ['dfthcsos__angle_k_1.kmb', 'dfthcsos__submission.npz'])
def test_one_tampered_input_blocks_every_write(data, tmp_path, victim):
    (data / INPUT_DIR / victim).write_bytes(b'x' * len(BLOBS[victim]))  # same size, other bytes
    out = tmp_path / 'out'
    with pytest.raises(ValueError, match='SHA-256'):
        generate.stage('dfthcsos', data, out, pin=_fixture_pin())
    assert not out.exists()


def test_wrong_size_is_rejected_before_writes(data, tmp_path):
    (data / INPUT_DIR / 'invsqrt.kmb').write_bytes(BLOBS['invsqrt.kmb'] + b'!')
    with pytest.raises(ValueError, match='size'):
        generate.stage('invsqrt', data, tmp_path / 'out', pin=_fixture_pin())
    assert not (tmp_path / 'out').exists()


def test_missing_input_is_rejected_before_writes(data, tmp_path):
    (data / INPUT_DIR / 'dfthcsos__angle_k_0.kmb').unlink()
    out = tmp_path / 'out'
    with pytest.raises(ValueError, match='missing'):
        generate.stage('dfthcsos', data, out, pin=_fixture_pin())
    assert not out.exists()


def test_all_problems_are_reported_together(data, tmp_path):
    (data / INPUT_DIR / 'dfthcsos__angle_k_0.kmb').unlink()
    (data / INPUT_DIR / 'dfthcsos__submission.npz').write_bytes(b'y' * len(BLOBS['dfthcsos__submission.npz']))
    with pytest.raises(ValueError) as caught:
        generate.stage('dfthcsos', data, tmp_path / 'out', pin=_fixture_pin())
    assert 'angle_k_0' in str(caught.value) and 'submission.npz' in str(caught.value)


def test_input_changed_during_copy_keeps_failed_artifact_and_deletes_nothing(data, tmp_path, monkeypatch):
    real = generate.preflight
    folder = data / INPUT_DIR

    def tamper_after_preflight(*args, **kwargs):
        plan = real(*args, **kwargs)
        (folder / 'dfthcsos__angle_k_1.kmb').write_bytes(b'z' * len(BLOBS['dfthcsos__angle_k_1.kmb']))
        return plan
    monkeypatch.setattr(generate, 'preflight', tamper_after_preflight)
    removed = []
    for owner, name in ((Path, 'unlink'), (Path, 'rmdir'), (os, 'remove'), (os, 'unlink'),
                        (os, 'rmdir'), (shutil, 'rmtree')):
        monkeypatch.setattr(owner, name, lambda *a, _n=name, **k: removed.append(_n))
    out = tmp_path / 'out'
    out.mkdir()
    with pytest.raises(ValueError, match='SHA-256'):
        generate.stage('dfthcsos', data, out, pin=_fixture_pin())
    monkeypatch.undo()
    assert removed == []  # soft-delete only: the stager never deletes anything
    tree = _tree(out)
    # no unverified bytes ever sit at a final submission name ...
    assert not any(name.endswith(('.kmb', '.npz')) for name in tree)
    # ... and the failed artifact is kept, visibly marked, for inspection
    kept = [name for name in tree if name.endswith('.partial')]
    assert 'dfthcsos/angle_k_1.kmb.partial' in kept
    assert tree['dfthcsos/angle_k_1.kmb.partial'] == b'z' * len(BLOBS['dfthcsos__angle_k_1.kmb'])


def test_retry_into_a_kept_failed_output_is_refused(data, tmp_path, monkeypatch):
    out = tmp_path / 'out'
    (out / 'dfthcsos').mkdir(parents=True)
    (out / 'dfthcsos/angle_k_0.kmb.partial').write_bytes(b'old failed run')
    with pytest.raises(FileExistsError):
        generate.stage('dfthcsos', data, out, pin=_fixture_pin())
    assert _tree(out) == {'dfthcsos/angle_k_0.kmb.partial': b'old failed run'}


def test_success_leaves_no_partial_files(data, tmp_path):
    generate.stage('dfthcsos', data, tmp_path / 'out', pin=_fixture_pin())
    assert not [n for n in _tree(tmp_path / 'out') if n.endswith('.partial')]


# --- staging: output cannot escape through links -------------------------------------------


def _link(target: Path, link: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        if sys.platform != 'win32':
            pytest.skip('symlinks unavailable')
        done = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)],
                              capture_output=True, text=True)
        if done.returncode != 0:
            pytest.skip('neither symlink nor junction can be created here')


def test_out_that_is_a_link_is_refused_and_nothing_escapes(data, tmp_path):
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    _link(elsewhere, tmp_path / 'out')
    with pytest.raises(FileExistsError):
        generate.stage('invsqrt', data, tmp_path / 'out', pin=_fixture_pin())
    assert list(elsewhere.iterdir()) == []


def test_task_directory_that_is_an_empty_link_is_refused_and_nothing_escapes(data, tmp_path):
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    out = tmp_path / 'out'
    out.mkdir()
    _link(elsewhere, out / 'dfthcsos')
    with pytest.raises(FileExistsError):
        generate.stage('dfthcsos', data, out, pin=_fixture_pin())
    assert list(elsewhere.iterdir()) == []


# --- staging: no overwrite -----------------------------------------------------------------


def test_occupied_output_fails_without_overwriting(data, tmp_path):
    out = tmp_path / 'out'
    out.mkdir()
    (out / 'invsqrt.kmb').write_bytes(b'previous')
    with pytest.raises(FileExistsError):
        generate.stage('invsqrt', data, out, pin=_fixture_pin())
    assert _tree(out) == {'invsqrt.kmb': b'previous'}


def test_occupied_dfthcsos_file_leaves_every_other_file_unwritten(data, tmp_path):
    out = tmp_path / 'out'
    (out / 'dfthcsos').mkdir(parents=True)
    (out / 'dfthcsos/angle_k_1.kmb').write_bytes(b'previous')
    with pytest.raises(FileExistsError):
        generate.stage('dfthcsos', data, out, pin=_fixture_pin())
    assert _tree(out) == {'dfthcsos/angle_k_1.kmb': b'previous'}


def test_stray_file_in_dfthcsos_directory_fails(data, tmp_path):
    out = tmp_path / 'out'
    (out / 'dfthcsos').mkdir(parents=True)
    (out / 'dfthcsos/stray.txt').write_bytes(b'stray')
    with pytest.raises(FileExistsError):
        generate.stage('dfthcsos', data, out, pin=_fixture_pin())
    assert _tree(out) == {'dfthcsos/stray.txt': b'stray'}


def test_other_tasks_files_in_out_do_not_block(data, tmp_path):
    out = tmp_path / 'out'
    out.mkdir()
    (out / 'dqi.kmb').write_bytes(b'someone else')
    generate.stage('invsqrt', data, out, pin=_fixture_pin())
    assert _tree(out) == {'dqi.kmb': b'someone else', 'invsqrt.kmb': BLOBS['invsqrt.kmb']}


def test_out_that_is_a_file_fails(data, tmp_path):
    out = tmp_path / 'out'
    out.write_bytes(b'file')
    with pytest.raises((FileExistsError, NotADirectoryError, ValueError)):
        generate.stage('invsqrt', data, out, pin=_fixture_pin())
    assert out.read_bytes() == b'file'


# --- supported tasks and CLI ---------------------------------------------------------------


def test_unsupported_task_is_rejected(data, tmp_path):
    with pytest.raises(ValueError, match='unsupported task'):
        generate.stage('search', data, tmp_path / 'out', pin=_fixture_pin())
    assert generate.TASKS == ('invsqrt', 'dqi', 'dfthcsos')


def test_cli_requires_explicit_task_and_out(tmp_path, capsys):
    for argv in ([], ['--out', str(tmp_path / 'o')], ['--task', 'invsqrt'],
                 ['--task', 'all', '--out', str(tmp_path / 'o')],
                 ['--task', 'search', '--out', str(tmp_path / 'o')]):
        with pytest.raises(SystemExit) as caught:
            generate.main(argv)
        assert caught.value.code == 2
    assert not (tmp_path / 'o').exists()


def test_cli_stages_and_prints_json(data, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(generate, 'PIN', _fixture_pin())
    monkeypatch.setenv('VQCC_DATA', str(data))
    code = generate.main(['--task', 'dqi', '--out', str(tmp_path / 'out')])
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report['task'] == 'dqi' and report['files'][0]['output'] == 'dqi.kmb'
    assert (tmp_path / 'out/dqi.kmb').read_bytes() == BLOBS['dqi.kmb']


def test_cli_data_flag_overrides_environment(data, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(generate, 'PIN', _fixture_pin())
    monkeypatch.setenv('VQCC_DATA', str(tmp_path / 'nowhere'))
    assert generate.main(['--task', 'invsqrt', '--out', str(tmp_path / 'out'),
                          '--data', str(data)]) == 0


def test_cli_failure_is_nonzero_and_writes_nothing(data, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(generate, 'PIN', _fixture_pin())
    (data / INPUT_DIR / 'invsqrt.kmb').write_bytes(b'q' * len(BLOBS['invsqrt.kmb']))
    code = generate.main(['--task', 'invsqrt', '--out', str(tmp_path / 'out'), '--data', str(data)])
    assert code != 0
    assert 'SHA-256' in capsys.readouterr().err
    assert not (tmp_path / 'out').exists()


def test_cli_without_any_data_root_is_a_usage_error(tmp_path, monkeypatch):
    monkeypatch.delenv('VQCC_DATA', raising=False)
    with pytest.raises(SystemExit) as caught:
        generate.main(['--task', 'invsqrt', '--out', str(tmp_path / 'out')])
    assert caught.value.code == 2


# --- malformed pins fail closed ------------------------------------------------------------


def _mutated(**edits):
    pin = copy.deepcopy(_fixture_pin())
    return pin, edits


@pytest.mark.parametrize('field,value', [
    ('sha256', 'ABC'), ('sha256', 'g' * 64), ('sha256', 'A' * 64),
    ('dataset_file', '../escape.kmb'), ('dataset_file', 'sub/dir.kmb'),
    ('output', '../invsqrt.kmb'), ('output', '/invsqrt.kmb'), ('output', 'other.kmb'),
    ('size_bytes', 0), ('size_bytes', '5'), ('kind', 'package'),
    ('task', 'search'),
])
def test_malformed_pin_entry_rejected_before_any_write(data, tmp_path, field, value):
    pin = _fixture_pin()
    entry = next(f for f in pin['files'] if f['dataset_file'] == 'invsqrt.kmb')
    entry[field] = value
    with pytest.raises(ValueError):
        generate.stage('invsqrt', data, tmp_path / 'out', pin=pin)
    assert not (tmp_path / 'out').exists()


def test_duplicate_digest_or_output_in_pin_is_rejected(data, tmp_path):
    pin = _fixture_pin()
    pin['files'][1]['sha256'] = pin['files'][0]['sha256']  # G5 maps digest -> path; must be unique
    with pytest.raises(ValueError, match='duplicate'):
        generate.stage('invsqrt', data, tmp_path / 'out', pin=pin)
    pin = _fixture_pin()
    pin['files'].append(dict(pin['files'][0], sha256='1' * 64))
    with pytest.raises(ValueError, match='duplicate'):
        generate.stage('invsqrt', data, tmp_path / 'out', pin=pin)


@pytest.mark.parametrize('bad', [
    None, [], 'x', {}, {'input_dir': 'inputs/x'}, {'input_dir': 'inputs/x', 'files': None},
    {'input_dir': 'inputs/x', 'files': 'x'}, {'input_dir': 'inputs/x', 'files': ['x']},
    {'input_dir': 5, 'files': []}, {'input_dir': 'inputs/x', 'files': [{'dataset_file': 5}]},
])
def test_structurally_malformed_pin_raises_value_error_not_a_crash(data, tmp_path, bad):
    with pytest.raises(ValueError):
        generate.stage('invsqrt', data, tmp_path / 'out', pin=bad)
    assert not (tmp_path / 'out').exists()


def test_cli_reports_a_malformed_pin_without_a_traceback(data, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(generate, 'PIN', {'input_dir': 'inputs/x'})
    code = generate.main(['--task', 'invsqrt', '--out', str(tmp_path / 'out'), '--data', str(data)])
    assert code == 1 and capsys.readouterr().err.startswith('error:')
    assert not (tmp_path / 'out').exists()


def test_circuit_suffix_must_be_vendored_circuit_kind():
    pin = _fixture_pin()
    next(f for f in pin['files'] if f['dataset_file'].endswith('.npz'))['kind'] = 'vendored_circuit'
    with pytest.raises(ValueError, match='kind'):
        generate.validate_pin(pin)


def test_input_dir_must_be_relative_without_traversal():
    for bad in ('/abs', '../up', 'a/../b', ''):
        pin = _fixture_pin()
        pin['input_dir'] = bad
        with pytest.raises(ValueError):
            generate.validate_pin(pin)


# --- the real SOURCE.json pins -------------------------------------------------------------


def test_source_json_carries_the_exact_hex_pins():
    pin = json.loads((REPO / 'tasks/public_portfolio/SOURCE.json').read_text())
    assert {f['dataset_file']: f['sha256'] for f in pin['files']} == EXPECTED
    assert all(re.fullmatch(r'[0-9a-f]{64}', f['sha256']) for f in pin['files'])
    assert pin['licence'] == 'Apache-2.0' and pin['licence_sha256'] == LICENCE_SHA256
    assert pin['readme_sha256'] == README_SHA256
    assert pin['source_url'] == SOURCE_URL and pin['version'] == '12'
    assert pin['input_dir'] == INPUT_DIR
    assert pin['licence_record'] == 'ledger/evidence/hermes-syed-v12/provenance.md'
    assert pin['sha256sums_entries'] == 23
    generate.validate_pin(pin)
    assert pin == generate.PIN


def test_source_json_task_map_and_sizes():
    by_task: dict[str, list[dict]] = {}
    for f in generate.PIN['files']:
        by_task.setdefault(f['task'], []).append(f)
    assert [f['output'] for f in by_task['invsqrt']] == ['invsqrt.kmb']
    assert [f['output'] for f in by_task['dqi']] == ['dqi.kmb']
    assert sorted(f['output'] for f in by_task['dfthcsos']) == sorted(
        [f'dfthcsos/angle_k_{k}.kmb' for k in range(15)] + ['dfthcsos/submission.npz'])
    sizes = {f['dataset_file']: f['size_bytes'] for f in generate.PIN['files']}
    assert sizes['invsqrt.kmb'] == 291626 and sizes['dqi.kmb'] == 455590024
    assert sizes['dfthcsos__submission.npz'] == 1847692
    assert sum(f['kind'] == 'vendored_circuit' for f in generate.PIN['files']) == 17


@pytest.mark.skipif(not DATASET_SUMS.is_file(), reason='local dataset copy not present')
def test_source_json_matches_dataset_sha256sums_text():
    listed = dict(reversed(line.split('  ', 1)) for line in DATASET_SUMS.read_text().splitlines() if line.strip())
    assert len(listed) == 23
    assert listed['LICENSE'] == LICENCE_SHA256 and listed['README.md'] == README_SHA256
    for name, digest in EXPECTED.items():
        assert listed[name] == digest
    assert hashlib.sha256(DATASET_SUMS.read_bytes()).hexdigest() == generate.PIN['sha256sums_sha256']


# --- gates ---------------------------------------------------------------------------------


def _install_fake_kickmix(monkeypatch, *, registers, num_qubits, toffoli=7):
    class Circuit:
        register_data = registers
        def __init__(self):
            self.num_qubits = num_qubits
        @classmethod
        def from_file(cls, path):
            cls.loaded = path
            return cls()
        def operation_statistics(self):
            return SimpleNamespace(num_toffoli_like=toffoli)
    module = ModuleType('kickmix')
    module.Circuit = Circuit
    monkeypatch.setitem(sys.modules, 'kickmix', module)
    return Circuit


def _pin_invsqrt_fixture(monkeypatch, blob=b'fixture invsqrt circuit'):
    pin = _fixture_pin()
    monkeypatch.setattr(generate, 'PIN', pin)
    monkeypatch.setattr(gates, 'PIN', pin, raising=False)
    return pin


def test_g1_invsqrt_rejects_wrong_bytes_before_parsing(tmp_path, monkeypatch):
    _pin_invsqrt_fixture(monkeypatch)
    circuit = _install_fake_kickmix(monkeypatch, registers={'x': range(22)}, num_qubits=46)
    (tmp_path / 'invsqrt.kmb').write_bytes(b'not the pinned circuit!!')
    result = gates.g1_invsqrt(tmp_path)
    assert result['status'].startswith('FAIL') and 'SHA-256' in result['status']
    assert not hasattr(circuit, 'loaded')


def test_g1_invsqrt_rejects_missing_file(tmp_path, monkeypatch):
    _pin_invsqrt_fixture(monkeypatch)
    assert gates.g1_invsqrt(tmp_path)['status'].startswith('FAIL')


def test_g1_invsqrt_passes_pinned_bytes_with_x22_and_46_qubits(tmp_path, monkeypatch):
    _pin_invsqrt_fixture(monkeypatch)
    _install_fake_kickmix(monkeypatch, registers={'x': range(22)}, num_qubits=46)
    (tmp_path / 'invsqrt.kmb').write_bytes(BLOBS['invsqrt.kmb'])
    result = gates.g1_invsqrt(tmp_path)
    assert result['status'] == 'PASS'
    assert result['num_qubits'] == 46 and result['max_qubits'] == 46
    assert result['sha256'] == hashlib.sha256(BLOBS['invsqrt.kmb']).hexdigest()


def test_g1_invsqrt_rejects_47_qubits(tmp_path, monkeypatch):
    _pin_invsqrt_fixture(monkeypatch)
    _install_fake_kickmix(monkeypatch, registers={'x': range(22)}, num_qubits=47)
    (tmp_path / 'invsqrt.kmb').write_bytes(BLOBS['invsqrt.kmb'])
    assert 'qubit' in gates.g1_invsqrt(tmp_path)['status']


@pytest.mark.parametrize('registers', [{'y': range(22)}, {'x': range(21)}, {'x': range(22), 'y': range(1)}, {}])
def test_g1_invsqrt_rejects_wrong_register_schema(tmp_path, monkeypatch, registers):
    _pin_invsqrt_fixture(monkeypatch)
    _install_fake_kickmix(monkeypatch, registers=registers, num_qubits=46)
    (tmp_path / 'invsqrt.kmb').write_bytes(BLOBS['invsqrt.kmb'])
    assert gates.g1_invsqrt(tmp_path)['status'].startswith('FAIL')


def test_g2_invsqrt_runs_the_bounded_vendored_spec(tmp_path, monkeypatch):
    _pin_invsqrt_fixture(monkeypatch)
    _install_fake_kickmix(monkeypatch, registers={'x': range(22)}, num_qubits=46)
    (tmp_path / 'invsqrt.kmb').write_bytes(BLOBS['invsqrt.kmb'])
    from dataclasses import dataclass
    seen = {}

    @dataclass(frozen=True)
    class Spec:
        n_p: int = 0
        max_x: int = 0
        shots_per_x: int = 0

        @classmethod
        def for_n_p(cls, n):
            return cls(n_p=n, max_x=999, shots_per_x=9)
    verifier = ModuleType('invsqrt.verify_submission_invsqrt')
    verifier.ProblemSpecInvSqrt = Spec

    def verify(circuit, spec, salt, max_workers):
        seen.update(spec=spec, salt=salt, max_workers=max_workers)
        return {'status': 'PASS'}
    verifier.verify = verify
    monkeypatch.setitem(sys.modules, 'invsqrt', ModuleType('invsqrt'))
    monkeypatch.setitem(sys.modules, 'invsqrt.verify_submission_invsqrt', verifier)
    result = gates.g2_invsqrt(tmp_path)
    assert result['parity'] is False and result['status'] == 'PASS'
    assert 'x=1..1536' in result['scope']
    assert seen['spec'] == Spec(n_p=10, max_x=1536, shots_per_x=1)
    assert seen['salt'] == 'PRA171_LOCAL_PUBLIC_FIXED_SALT_0001'
    assert seen['max_workers'] == 1


def test_g2_invsqrt_fails_closed_when_g1_fails(tmp_path, monkeypatch):
    _pin_invsqrt_fixture(monkeypatch)
    (tmp_path / 'invsqrt.kmb').write_bytes(b'wrong!!')
    result = gates.g2_invsqrt(tmp_path)
    assert result['status'].startswith('FAIL')


def test_bounded_spec_matches_the_vendored_path():
    from dataclasses import dataclass, replace

    @dataclass(frozen=True)
    class Spec:
        max_x: int = 0
        shots_per_x: int = 0

        @classmethod
        def for_n_p(cls, n):
            return cls(max_x=999, shots_per_x=9)
    spec = gates._bounded_spec(Spec)
    assert (spec.max_x, spec.shots_per_x) == (1536, 1)
    assert replace(Spec.for_n_p(10), max_x=1536, shots_per_x=1) == spec


# --- gate config ---------------------------------------------------------------------------


@pytest.fixture(scope='module')
def config():
    return load_config(CONFIG)


@pytest.fixture(scope='module')
def raw():
    return yaml.safe_load(CONFIG.read_text())


def test_config_loads_with_g0_to_g5_in_order(config):
    assert [g.id for g in config.gates] == ['G0', 'G1', 'G2', 'G3', 'G4', 'G5']


def test_config_waives_no_gate(config):
    assert [g.id for g in config.gates if g.waivable] == []


def test_config_g0_g3_g4_g5_checks_are_the_existing_ones(config, raw):
    checks = {g.id: g.check for g in config.gates}
    assert checks['G0'] == 'ledger.gates.checks:g0_preflight'
    assert checks['G3'] == 'ledger.gates.checks:g3_full_verifier'
    assert checks['G4'] == 'ledger.gates.checks:g4_strict_improvement'
    assert checks['G5'] == 'ledger.gates.checks:g5_rebuild_and_provenance'
    reference = yaml.safe_load((REPO / 'configs/gates/reference.yaml').read_text())
    ref = {g['id']: g for g in reference['gates']}
    mine = {g['id']: g for g in raw['gates']}
    for gate in ('G0', 'G3', 'G5'):
        assert mine[gate]['params'] == ref[gate]['params'] or gate == 'G3'
    assert mine['G5']['params'] == {'timeout_seconds': 7200}
    assert mine['G0']['params'] == {'hook': 'ledger.gates.g0_preflight:preflight'}


def test_config_g3_shots_unchanged_from_the_accepted_pipeline(raw):
    shots = next(g for g in raw['gates'] if g['id'] == 'G3')['params']['expected_shots']
    assert shots == {'invsqrt': 200540928, 'dqi': 102400, 'dfthcsos': 78080}
    vendored = yaml.safe_load((REPO / 'configs/gates/pra325-invsqrt-vendored-63q.yaml').read_text())
    assert next(g for g in vendored['gates'] if g['id'] == 'G3') == next(
        g for g in raw['gates'] if g['id'] == 'G3')


def test_config_g1_g2_hooks(raw):
    g1 = next(g for g in raw['gates'] if g['id'] == 'G1')['params']['hooks']
    g2 = next(g for g in raw['gates'] if g['id'] == 'G2')['params']['hooks']
    assert g1 == {'invsqrt': 'tasks.public_portfolio.gates:g1_invsqrt',
                  'dqi': 'tasks.dqi.gates:g1_smoke',
                  'dfthcsos': 'tasks.dfthcsos.gates:g1_smoke'}
    assert g2 == {'invsqrt': 'tasks.public_portfolio.gates:g2_invsqrt',
                  'dqi': 'tasks.dqi.gates:g2_proxy',
                  'dfthcsos': 'tasks.dfthcsos.gates:g2_proxy'}


def test_every_configured_hook_resolves(config):
    import importlib
    for spec in config.gates:
        names = [spec.check] + list((spec.params.get('hooks') or {}).values())
        if 'hook' in spec.params:
            names.append(spec.params['hook'])
        for name in names:
            module, _, function = name.partition(':')
            if module in {'harness.score_local', 'ledger.gates.g0_preflight'}:
                continue  # owned by the parent, which also installs kickmix
            assert callable(getattr(importlib.import_module(module), function)), name


def test_config_generators_use_the_explicit_per_task_cli(config):
    for task in generate.TASKS:
        assert config.generators[task] == [
            '{python}', '-m', 'tasks.public_portfolio.generate',
            '--task', task, '--out', '{out}']


def test_config_declares_seventeen_vendored_circuits_and_the_npz(config):
    entries = config.inputs
    assert set(entries) == {'invsqrt', 'dqi', 'dfthcsos'}
    flat = [e for task in entries.values() for e in task]
    vendored = [e for e in flat if e.get('kind') == 'vendored_circuit']
    assert len(vendored) == 17 and len(flat) == 18
    assert len(entries['invsqrt']) == 1 and len(entries['dqi']) == 1 and len(entries['dfthcsos']) == 16
    for e in vendored:
        assert e['path'].endswith('.kmb')
        assert e['source_url'] == SOURCE_URL and e['version'] == '12'
        assert e['licence'] == 'Apache-2.0'
        assert e['licence_record'] == 'ledger/evidence/hermes-syed-v12/provenance.md'
    (npz,) = [e for e in flat if e not in vendored]
    assert npz == {'path': f'{INPUT_DIR}/dfthcsos__submission.npz',
                   'sha256': EXPECTED['dfthcsos__submission.npz']}
    assert vendored_circuit_licence_problems(entries) == []


def test_config_inputs_equal_source_json_pins(config):
    by_path = {e['path']: e['sha256'] for task in config.inputs.values() for e in task}
    assert by_path == {f"{INPUT_DIR}/{name}": digest for name, digest in EXPECTED.items()}
    for task, entries in config.inputs.items():
        wanted = {f"{INPUT_DIR}/{f['dataset_file']}" for f in generate.PIN['files'] if f['task'] == task}
        assert {e['path'] for e in entries} == wanted


def test_config_input_paths_are_the_stage_paths(config):
    for f in generate.PIN['files']:
        assert f"{generate.PIN['input_dir']}/{f['dataset_file']}" in {
            e['path'] for e in config.inputs[f['task']]}


def test_config_has_no_banned_source_markers(raw):
    text = CONFIG.read_text().lower()
    assert 'k256' not in text


# --- provenance and notice -----------------------------------------------------------------


def test_provenance_record_names_every_pin_and_limits_the_claims():
    text = PROVENANCE.read_text(encoding='utf-8')
    assert SOURCE_URL in text and LICENCE_SHA256 in text and README_SHA256 in text
    for name, digest in EXPECTED.items():
        assert digest in text and name in text
    assert generate.PIN['sha256sums_sha256'] in text
    assert 'Syed Asad Ali' in text
    lowered = text.lower()
    assert 'author-claimed' in lowered or 'author claimed' in lowered
    assert 'not independently' in lowered or 'not certified' in lowered
    assert 'D-HERMES-20261112-02' in text and 'D-PRA341-01' in text
    assert 'k256' in lowered  # the exclusion is restated, not silently dropped
    assert '23' in text


def test_notice_is_one_valid_bullet_file():
    text = NOTICE.read_text(encoding='utf-8')
    assert text.endswith('\n') and text.strip()
    assert all(line.startswith('- ') for line in text.splitlines())
    assert 'Syed Asad Ali' in text and SOURCE_URL in text and 'Apache' in text
    assert LICENCE_SHA256 in text
    assert re.fullmatch(r'\d{2}-[a-z0-9][a-z0-9-]*\.txt', NOTICE.name)
