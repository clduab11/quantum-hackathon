# SPDX-License-Identifier: Apache-2.0
"""The three-source public mix hermes-mix-20261113 (D-HERMES-20261113-01).

The stager takes a pin map with several sources, each in its own input directory, selected on
the command line with ``--pin``. The real pin map, gate config, runner, provenance record,
decision file and notice are checked here. Staging tests use tiny fixture bytes; no real
circuit is loaded or verified.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from ledger.benchmark_health import declared_input_problems
from ledger.gates.runner import load_config
from ledger.registers import decision_rows
from ledger.run_manifest import vendored_circuit_licence_problems
from tasks.public_portfolio import gates, generate

REPO = Path(__file__).resolve().parents[1]
MIX_NAME = 'MIX-20261113.json'
MIX_PATH = REPO / 'tasks/public_portfolio' / MIX_NAME
CONFIG = REPO / 'configs/gates/hermes-mix-20261113.yaml'
RUNNER = REPO / 'ledger/evidence/hermes-mix-20261113/run_candidate.py'
PROVENANCE = REPO / 'ledger/evidence/hermes-mix-20261113/provenance.md'
DECISION = REPO / 'docs/decisions/D-HERMES-20261113-01.md'
DEC02 = REPO / 'docs/decisions/D-HERMES-20261112-02.md'
NOTICE = REPO / 'notices/51-public-mix.txt'
RECORD = 'ledger/evidence/hermes-mix-20261113/provenance.md'

AHOIRG = 'inputs/ahoirg/qcc-submit-verify-and-package-v25'
AREEBBB = 'inputs/areebbb/qai-fewer-toffolis-same-qubits-lb-27-11042-v8'
ATAKAN = 'inputs/atakanaldemir/quantum-circuits-iso-gap-dqi-h5-v19'
SOURCES = {
    'ahoirg-v25': ('https://www.kaggle.com/code/ahoirg/qcc-submit-verify-and-package', '25', AHOIRG),
    'areebbb-v8': ('https://www.kaggle.com/code/areebbb/qai-fewer-toffolis-same-qubits-lb-27-11042',
                   '8', AREEBBB),
    'atakanaldemir-v19': ('https://www.kaggle.com/code/atakanaldemir/quantum-circuits-iso-gap-dqi-h5',
                          '19', ATAKAN),
}

# Measured on 2026-11-13 from the staged notebook outputs (the angle circuits were extracted from
# the Atakan V19 output zip and are byte-identical to maoxin123's V6 pins).
EXPECTED = {
    ('ahoirg-v25', 'invsqrt.kmb'):
        ('4560ac0c017bf6d1bf27c73320f2e30c247a2a18143d58ff92a601f8bc20b218', 198590),
    ('areebbb-v8', 'dqi.kmb'):
        ('821bf8d157c03c3e868a0099b0ab1438cfba664ab1bc6fec3210654099b672a3', 455584321),
    ('atakanaldemir-v19', 'dfthcsos__submission.npz'):
        ('b9dbe922ddeeaa9b547557bc273f9ed0f8c8870a00ad019ad9352024318c2800', 1847692),
}
ANGLES = {
    0: ('6de2263fd8fec08b292fbfa28256e6ae2ec154d562d2a23f251ed73ebf72c307', 181417),
    1: ('72441bd102c19182020971625cb5ed2bd15295bd68f404b1c298f49cbdf7e365', 419554),
    2: ('4f2a0e2c1dbb50f6f80f512a007a09749776243068b2f1ded0547d51d253dfdd', 159130),
    3: ('2b7d2a3b491fcdd24fc0fa5d571af37eb0ec0dc7ace8511a2c17f78d222201d3', 417882),
    4: ('36aa71eda15079d667b8899d86852b620ca9b79e42a129b2541dbe5771559f43', 352678),
    5: ('24e00cc686d7c77c08659c30a3246e45ab2843da17c461c0ca869b80a2735799', 351034),
    6: ('b6f5d04a4ce3f83b7edeac2757f273d31fa1023a8c36ac5b51ba8213af47534f', 356091),
    7: ('d7fdb33739cecefc698b89fbebe484ac7b9980c6c98a0b89fb31421ba3b87211', 351214),
    8: ('5a1bbec912aca17bec21aed486fec540be47db9e739ea51dee85e01bb0cdb620', 348595),
    9: ('741b39f754917ece2a6c7b62b2d22e847641b9ecabe59a16bfaefc77fffdb6e8', 347033),
    10: ('6ea51da00b346e193c5cb547032bacec4f5f9205eb087732389be9126bcf8f6b', 349146),
    11: ('c53b1ede451efffba10cf667749b2dbec0fa4cd73b87e8b0f78d141920fbd063', 352676),
    12: ('4dd120c4e2e908965101cd4268982d3141eba13507409ee56ff42271b3e16bd4', 350286),
    13: ('ada8c4e6ffbd3ac856af2a75e342b66be4403c5d3f828c0821ec902ea7387425', 347322),
    14: ('9a60cb59c602f05b058a4a4c463773b5fb9cb334afbee72c493d380945b7926b', 355502),
}
for _k, _pin in ANGLES.items():
    EXPECTED[('atakanaldemir-v19', f'dfthcsos__angle_k_{_k}.kmb')] = _pin
INPUT_DIRS = {source: folder for source, (_, _, folder) in SOURCES.items()}
V12_INVSQRT = '321aff83636214196daa9cbc9dcc9c5e12a155bcff8d9989e98b8cee40935177'

BLOBS = {
    ('one', 'invsqrt.kmb'): b'fixture mix invsqrt',
    ('two', 'dqi.kmb'): b'fixture mix dqi ' * 2,
    ('three', 'dfthcsos__angle_k_0.kmb'): b'fixture mix angle zero',
    ('three', 'dfthcsos__submission.npz'): b'fixture mix factor',
}
FIXTURE_DIRS = {'one': 'inputs/a/one-v1', 'two': 'inputs/b/two-v2', 'three': 'inputs/c/three-v3'}


def _fixture_pin() -> dict:
    sources = {name: {'owner': name, 'version': '1', 'licence': 'Apache-2.0',
                      'source_url': f'https://example.invalid/{name}', 'input_dir': folder}
               for name, folder in FIXTURE_DIRS.items()}
    files = []
    for (source, name), blob in BLOBS.items():
        task = 'dfthcsos' if name.startswith('dfthcsos__') else name.removesuffix('.kmb')
        files.append({'source': source, 'dataset_file': name, 'task': task,
                      'output': name.replace('__', '/', 1),
                      'kind': 'vendored_circuit' if name.endswith('.kmb') else 'package_input',
                      'sha256': hashlib.sha256(blob).hexdigest(), 'size_bytes': len(blob)})
    return {'kind': 'vendored_circuit', 'licence_record': 'fixture-record', 'sources': sources,
            'files': files}


@pytest.fixture
def data(tmp_path):
    root = tmp_path / 'data'
    for (source, name), blob in BLOBS.items():
        folder = root / FIXTURE_DIRS[source]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(blob)
    return root


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob('*')) if p.is_file()}


# --- several sources -------------------------------------------------------------------------


def test_each_task_is_staged_from_its_own_source_directory(data, tmp_path):
    pin = _fixture_pin()
    for task in generate.TASKS:
        generate.stage(task, data, tmp_path / 'out', pin=pin)
    assert _tree(tmp_path / 'out') == {
        'invsqrt.kmb': BLOBS[('one', 'invsqrt.kmb')],
        'dqi.kmb': BLOBS[('two', 'dqi.kmb')],
        'dfthcsos/angle_k_0.kmb': BLOBS[('three', 'dfthcsos__angle_k_0.kmb')],
        'dfthcsos/submission.npz': BLOBS[('three', 'dfthcsos__submission.npz')],
    }


def test_report_names_the_source_of_every_file(data, tmp_path):
    report = generate.stage('dqi', data, tmp_path / 'out', pin=_fixture_pin())
    assert report['files'] == [{'output': 'dqi.kmb', 'source': 'two',
                                'sha256': hashlib.sha256(BLOBS[('two', 'dqi.kmb')]).hexdigest(),
                                'size_bytes': len(BLOBS[('two', 'dqi.kmb')])}]


def test_a_file_in_the_wrong_source_directory_is_missing(data, tmp_path):
    pin = _fixture_pin()
    next(f for f in pin['files'] if f['task'] == 'invsqrt')['source'] = 'two'
    with pytest.raises(ValueError, match='missing'):
        generate.stage('invsqrt', data, tmp_path / 'out', pin=pin)
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('edit', [
    lambda p: p['files'][0].update(source='nowhere'),
    lambda p: p['files'][0].pop('source'),
    lambda p: p['sources']['one'].update(input_dir='../escape'),
    lambda p: p['sources']['one'].update(input_dir='/abs'),
    lambda p: p['sources']['one'].pop('input_dir'),
    lambda p: p.update(sources=['one']),
    lambda p: p.update(sources={}),
    lambda p: p['sources'].update(bad='x'),
])
def test_malformed_sources_fail_closed_before_any_write(data, tmp_path, edit):
    pin = copy.deepcopy(_fixture_pin())
    edit(pin)
    with pytest.raises(ValueError):
        generate.stage('invsqrt', data, tmp_path / 'out', pin=pin)
    assert not (tmp_path / 'out').exists()


def test_the_same_file_name_may_come_from_two_sources_but_outputs_stay_unique():
    pin = _fixture_pin()
    clone = dict(pin['files'][0], source='two', sha256='1' * 64)
    pin['files'].append(clone)
    with pytest.raises(ValueError, match='duplicate output'):
        generate.validate_pin(pin)


# --- --pin on the command line ----------------------------------------------------------------


def test_cli_pin_selects_a_pin_file_beside_the_stager(data, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(generate, 'load_pin', lambda name: _fixture_pin() if name == 'X.json' else None)
    code = generate.main(['--pin', 'X.json', '--task', 'invsqrt', '--out', str(tmp_path / 'out'),
                          '--data', str(data)])
    assert code == 0, capsys.readouterr().err
    assert (tmp_path / 'out/invsqrt.kmb').read_bytes() == BLOBS[('one', 'invsqrt.kmb')]


@pytest.mark.parametrize('name', ['../SOURCE.json', 'sub/x.json', 'C:/x.json', 'x.txt', '.json', ''])
def test_load_pin_accepts_only_a_bare_json_name(name):
    with pytest.raises(ValueError):
        generate.load_pin(name)


def test_load_pin_reads_the_committed_files():
    assert generate.load_pin('SOURCE.json') == generate.PIN
    assert generate.load_pin(MIX_NAME) == json.loads(MIX_PATH.read_text(encoding='utf-8'))


def test_cli_without_pin_keeps_the_v12_default(data, tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(generate, 'stage', lambda task, d, out, pin=None: seen.update(pin=pin) or {})
    assert generate.main(['--task', 'dqi', '--out', str(tmp_path / 'o'), '--data', str(data)]) == 0
    assert seen['pin'] is None  # stage() then falls back to SOURCE.json


# --- the real pin map ---------------------------------------------------------------------------


@pytest.fixture(scope='module')
def mix():
    return json.loads(MIX_PATH.read_text(encoding='utf-8'))


def test_mix_pins_are_exact(mix):
    generate.validate_pin(mix)
    got = {(f['source'], f['dataset_file']): (f['sha256'], f['size_bytes']) for f in mix['files']}
    assert got == EXPECTED
    assert sum(f['kind'] == 'vendored_circuit' for f in mix['files']) == 17
    (npz,) = [f for f in mix['files'] if f['kind'] == 'package_input']
    assert npz['output'] == 'dfthcsos/submission.npz'


def test_mix_task_map(mix):
    by_task: dict[str, set] = {}
    for f in mix['files']:
        by_task.setdefault(f['task'], set()).add((f['source'], f['output']))
    assert by_task['invsqrt'] == {('ahoirg-v25', 'invsqrt.kmb')}
    assert by_task['dqi'] == {('areebbb-v8', 'dqi.kmb')}
    assert by_task['dfthcsos'] == {('atakanaldemir-v19', f'dfthcsos/angle_k_{k}.kmb')
                                   for k in range(15)} | {('atakanaldemir-v19', 'dfthcsos/submission.npz')}


def test_mix_sources_are_pinned_by_url_version_and_licence(mix):
    assert set(mix['sources']) == set(SOURCES)
    for name, (url, version, folder) in SOURCES.items():
        source = mix['sources'][name]
        assert (source['source_url'], source['version'], source['input_dir']) == (url, version, folder)
        assert source['licence'] == 'Apache-2.0'
        assert re.fullmatch(r'[0-9a-f]{64}', source['output_zip_sha256'])
    assert mix['licence_record'] == RECORD


def test_mix_never_ships_the_v12_invsqrt(mix):
    assert V12_INVSQRT not in {f['sha256'] for f in mix['files']}


# --- gates --------------------------------------------------------------------------------------


def _fake_kickmix(monkeypatch, num_qubits=46):
    import sys
    from types import ModuleType

    class Circuit:
        register_data = {'x': range(22)}

        def __init__(self):
            self.num_qubits = num_qubits

        @classmethod
        def from_file(cls, path):
            return cls()

        def operation_statistics(self):
            return SimpleNamespace(num_toffoli_like=3)

    module = ModuleType('kickmix')
    module.Circuit = Circuit
    monkeypatch.setitem(sys.modules, 'kickmix', module)


def test_mix_invsqrt_hooks_check_the_mix_pin_not_the_v12_pin(tmp_path, monkeypatch):
    pin = _fixture_pin()
    monkeypatch.setattr(gates, 'mix_pin', lambda: pin)
    _fake_kickmix(monkeypatch)
    (tmp_path / 'invsqrt.kmb').write_bytes(BLOBS[('one', 'invsqrt.kmb')])
    result = gates.g1_mix_invsqrt(tmp_path)
    assert result['status'] == 'PASS'
    assert result['sha256'] == hashlib.sha256(BLOBS[('one', 'invsqrt.kmb')]).hexdigest()
    assert gates.g1_invsqrt(tmp_path)['status'].startswith('FAIL')  # v12 pin still guards v12
    (tmp_path / 'invsqrt.kmb').write_bytes(b'x' * len(BLOBS[('one', 'invsqrt.kmb')]))
    assert gates.g1_mix_invsqrt(tmp_path)['status'].startswith('FAIL')
    assert gates.g2_mix_invsqrt(tmp_path)['status'].startswith('FAIL')


def test_mix_pin_is_the_committed_file():
    assert gates.mix_pin() == json.loads(MIX_PATH.read_text(encoding='utf-8'))


# --- gate config ---------------------------------------------------------------------------------


@pytest.fixture(scope='module')
def config():
    return load_config(CONFIG)


@pytest.fixture(scope='module')
def raw():
    return yaml.safe_load(CONFIG.read_text(encoding='utf-8'))


def test_config_gates_are_the_v12_gates_with_mix_invsqrt_hooks(config, raw):
    assert [g.id for g in config.gates] == ['G0', 'G1', 'G2', 'G3', 'G4', 'G5']
    assert [g.id for g in config.gates if g.waivable] == []
    v12 = yaml.safe_load((REPO / 'configs/gates/hermes-syed-v12.yaml').read_text(encoding='utf-8'))
    mine = {g['id']: g for g in raw['gates']}
    theirs = {g['id']: g for g in v12['gates']}
    for gate in ('G0', 'G3', 'G4', 'G5'):
        assert mine[gate] == theirs[gate]
    assert raw['salt_label'] == v12['salt_label']
    assert mine['G1']['params']['hooks'] == {'invsqrt': 'tasks.public_portfolio.gates:g1_mix_invsqrt',
                                             'dqi': 'tasks.dqi.gates:g1_smoke',
                                             'dfthcsos': 'tasks.dfthcsos.gates:g1_smoke'}
    assert mine['G2']['params']['hooks'] == {'invsqrt': 'tasks.public_portfolio.gates:g2_mix_invsqrt',
                                             'dqi': 'tasks.dqi.gates:g2_proxy',
                                             'dfthcsos': 'tasks.dfthcsos.gates:g2_proxy'}


def test_config_generators_stage_from_the_mix_pin(config):
    for task in generate.TASKS:
        assert config.generators[task] == ['{python}', '-m', 'tasks.public_portfolio.generate',
                                           '--pin', MIX_NAME, '--task', task, '--out', '{out}']


def test_config_inputs_equal_the_mix_pins(config, mix):
    flat = {e['path']: (task, e) for task, entries in config.inputs.items() for e in entries}
    want = {f"{INPUT_DIRS[f['source']]}/{f['dataset_file']}": f for f in mix['files']}
    assert set(flat) == set(want)
    for path, (task, entry) in flat.items():
        pin = want[path]
        assert task == pin['task'] and entry['sha256'] == pin['sha256']
        assert declared_input_problems(task, entry) == []
        if pin['kind'] == 'vendored_circuit':
            url, version, _ = SOURCES[pin['source']]
            assert entry == {'kind': 'vendored_circuit', 'path': path, 'sha256': pin['sha256'],
                             'source_url': url, 'version': version, 'licence': 'Apache-2.0',
                             'licence_record': RECORD}
        else:
            assert entry == {'path': path, 'sha256': pin['sha256']}
    assert vendored_circuit_licence_problems(config.inputs) == []
    assert 'k256' not in CONFIG.read_text(encoding='utf-8').lower()


# --- runner --------------------------------------------------------------------------------------


def _runner():
    spec = importlib.util.spec_from_file_location('hermes_mix_run_candidate', RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runner_identity():
    run = _runner()
    assert run.CANDIDATE_ID == 'hermes-mix-20261113' and run.PARENT_ID == 'hermes-syed-v12'
    assert run.CONFIG == CONFIG and run.SOURCE == MIX_PATH
    assert re.fullmatch(r'[0-9a-f]{64}', run.ZIP_SHA256) and run.ZIP_SIZE > 0
    for rel in ('tasks/public_portfolio', 'configs/gates/hermes-mix-20261113.yaml',
                'ledger/evidence/hermes-mix-20261113/run_candidate.py', RECORD,
                'docs/decisions/D-HERMES-20261113-01.md', 'notices/51-public-mix.txt',
                'ledger/benchmark_health.py', 'ledger/gates', 'harness'):
        assert rel in run.CANDIDATE_PATHS
    assert 'ledger/evidence/hermes-mix-20261113' not in run.CANDIDATE_PATHS


def test_runner_refuses_another_zip(tmp_path):
    other = tmp_path / 'other.zip'
    other.write_bytes(b'not the mix')
    with pytest.raises(ValueError, match='expected the built candidate'):
        _runner().check_zip(other)


def test_runner_pins_and_provenance_per_task():
    run = _runner()
    expected = run.pinned_files()
    assert expected['invsqrt'] == {'invsqrt.kmb': EXPECTED[('ahoirg-v25', 'invsqrt.kmb')][0]}
    assert expected['dqi'] == {'dqi.kmb': EXPECTED[('areebbb-v8', 'dqi.kmb')][0]}
    assert len(expected['dfthcsos']) == 16
    manifest = SimpleNamespace(tasks={t: SimpleNamespace(files=dict(f)) for t, f in expected.items()})
    run.check_pins(manifest)
    manifest.tasks['dqi'].files = {'dqi.kmb': '0' * 64}
    with pytest.raises(ValueError, match='dqi'):
        run.check_pins(manifest)
    provenance = run.provenance()
    assert provenance['invsqrt'].parent_url == SOURCES['ahoirg-v25'][0]
    assert provenance['dqi'].parent_url == SOURCES['areebbb-v8'][0]
    assert provenance['dfthcsos'].parent_url == SOURCES['atakanaldemir-v19'][0]
    for record in provenance.values():
        assert record.licence == 'Apache-2.0' and 'not certified' in record.notes


def test_runner_refuses_uncommitted_candidate_paths(monkeypatch):
    run = _runner()
    monkeypatch.setattr(run.subprocess, 'check_output', lambda argv, **kw: '?? x\n')
    with pytest.raises(ValueError, match='commit the candidate'):
        run.check_committed()


# --- records -------------------------------------------------------------------------------------


def test_decision_records_the_deferred_licence_review():
    (row,) = [r for r in decision_rows(REPO) if r.id == 'D-HERMES-20261113-01']
    text = DECISION.read_text(encoding='utf-8')
    assert len([ln for ln in text.splitlines() if ln.strip()]) == 1
    for needle in ('2027-01-20', 'licen', 'deferred', 'D-HERMES-20261112-02', 'ahoirg', 'areebbb',
                   'atakanaldemir', 'maoxin123', '4560ac0c', '821bf8d1', 'b9dbe922'):
        assert needle in text, needle
    assert row.date == '2026-11-13'


def test_the_v12_ruling_is_untouched():
    assert hashlib.sha256(DEC02.read_bytes()).hexdigest() == (
        '785dd18b892bbd56c2db3de619c9a9785b70483a161f660345c71da9f6a80946')


def test_provenance_names_every_pin_source_and_limit(mix):
    text = PROVENANCE.read_text(encoding='utf-8')
    for f in mix['files']:
        assert f['sha256'] in text and f['dataset_file'] in text
    for name, (url, version, _) in SOURCES.items():
        assert url in text and mix['sources'][name]['output_zip_sha256'] in text
    lowered = text.lower()
    assert 'not certified' in lowered and '2027-01-20' in text and 'D-HERMES-20261113-01' in text
    assert 'k256' in lowered  # the k256.dev exclusion is restated


def test_notice_is_one_valid_bullet_file():
    text = NOTICE.read_text(encoding='utf-8')
    assert text.endswith('\n') and all(line.startswith('- ') for line in text.splitlines())
    for needle in ('Ali Haydar', 'Areeb Ali', 'Atakan Aldemir', 'maoxin123', 'Syed Asad Ali',
                   'Apache', SOURCES['ahoirg-v25'][0], SOURCES['areebbb-v8'][0],
                   SOURCES['atakanaldemir-v19'][0]):
        assert needle in text, needle
