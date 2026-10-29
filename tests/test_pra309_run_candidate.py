"""Fresh-checkout and resume paths for the PRA-321 candidate runner."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'ledger/evidence/pra309-chem-8-143-60/run_candidate.py'


def load():
    spec = importlib.util.spec_from_file_location('pra309_run_candidate', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Task:
    def __init__(self, files):
        self.files = files


class _Manifest:
    def __init__(self, generator_commit='a' * 40, zip_sha256='abc'):
        self.tasks = {
            'invsqrt': _Task({'invsqrt.kmb': '1'}),
            'dqi': _Task({'dqi.kmb': '2'}),
            'dfthcsos': _Task({'dfthcsos/angle_k_0.kmb': '3'}),
        }
        self.generator_commit = generator_commit
        self.geometric_mean = 19.2
        self.zip_sha256 = zip_sha256
        provenance = SimpleNamespace(licence='Apache-2.0', parent_url='https://example.test', notes='n')
        for task in self.tasks.values():
            task.provenance = provenance

    def shipping_problems(self):
        return []


def _locations(tmp_path):
    return {
        'data': tmp_path / 'data',
        'parent_zip': tmp_path / 'data' / 'pra294-c59' / 'pra294-c59.zip',
        'zip': tmp_path / 'data' / 'pra309-chem-8-143-60' / 'pra309-chem-8-143-60.zip',
        'manifest': tmp_path / 'manifest.json',
        'config': tmp_path / 'gates.yaml',
        'parent_manifest': tmp_path / 'parent.json',
        'pipeline': tmp_path / 'pipeline.json',
    }


def _bind(monkeypatch, module, loc, parent, built, writes, pipeline_records):
    monkeypatch.setattr(module, 'candidate_paths', lambda root=None: loc)
    monkeypatch.setattr(module, 'load_config', lambda path: SimpleNamespace(salt_label='salt'))
    monkeypatch.setattr(module, 'read_manifest', lambda path: parent if path == loc['parent_manifest'] else built['manifest'])

    def build(parent_manifest, paths):
        assert parent_manifest is parent
        paths['zip'].parent.mkdir(parents=True, exist_ok=True)
        paths['zip'].write_bytes(b'zip-bytes')
        built['build_calls'] += 1
        return {'files': {'dfthcsos/angle_k_0.kmb': {'sha256': '3'}}}

    def start_candidate(*args, **kwargs):
        built['start_args'] = (args, kwargs)
        return built['manifest']

    def write_manifest(manifest, path, exclusive=False):
        writes.append((path, exclusive, manifest.generator_commit))
        path.write_text('manifest\n')

    def run_pipeline(*args, **kwargs):
        built['pipeline_args'] = (args, kwargs)
        return pipeline_records

    monkeypatch.setattr(module, 'build', build)
    monkeypatch.setattr(module, 'start_candidate', start_candidate)
    monkeypatch.setattr(module, 'write_manifest', write_manifest)
    monkeypatch.setattr(module, 'run_pipeline', run_pipeline)
    monkeypatch.setattr(module, 'sha256_file', lambda path: 'abc' if path == loc['zip'] else parent.zip_sha256)
    monkeypatch.setattr(module, 'require_generator_paths', lambda commit: built.setdefault('checked', []).append(commit))


def test_data_root_honours_vqcc_data(monkeypatch, tmp_path):
    module = load()
    monkeypatch.setenv('VQCC_DATA', str(tmp_path / 'elsewhere'))
    assert module.data_root() == tmp_path / 'elsewhere'
    paths = module.candidate_paths()
    assert paths['zip'] == tmp_path / 'elsewhere' / 'pra309-chem-8-143-60' / 'pra309-chem-8-143-60.zip'
    assert paths['parent_zip'] == tmp_path / 'elsewhere' / 'pra294-c59' / 'pra294-c59.zip'


def test_fresh_clone_writes_the_manifest_exclusively(monkeypatch, tmp_path, capsys):
    module = load()
    loc = _locations(tmp_path)
    parent = _Manifest()
    created = _Manifest(generator_commit='b' * 40)
    built = {'manifest': created, 'build_calls': 0}
    writes = []
    record = SimpleNamespace(gate='G0', status='PASS', reason='')
    _bind(monkeypatch, module, loc, parent, built, writes, [record])
    module.main(['--generator-commit', 'c' * 40])
    assert built['build_calls'] == 1
    assert writes == [(loc['manifest'], True, 'c' * 40)]
    assert built['checked'] == ['c' * 40]
    assert 'start_args' in built
    saved = json.loads(loc['pipeline'].read_text())
    assert saved['gates'] == [{'gate': 'G0', 'status': 'PASS', 'reason': ''}]
    assert 'preserved_pipeline' not in saved
    assert json.loads(capsys.readouterr().out)['gates'][0]['gate'] == 'G0'


def test_resume_rebuilds_a_missing_zip_without_rewriting_the_manifest(monkeypatch, tmp_path):
    module = load()
    loc = _locations(tmp_path)
    loc['manifest'].write_text('existing manifest\n')
    parent = _Manifest()
    existing = _Manifest()
    built = {'manifest': existing, 'build_calls': 0}
    writes = []
    record = SimpleNamespace(gate='G5', status='PASS', reason='')
    _bind(monkeypatch, module, loc, parent, built, writes, [record])
    module.main(['--generator-commit', existing.generator_commit])
    assert built['build_calls'] == 1
    assert writes == []
    assert loc['manifest'].read_text() == 'existing manifest\n'
    assert built['pipeline_args'][0][0] is existing
    assert json.loads(loc['pipeline'].read_text())['gates'][0]['gate'] == 'G5'


def test_resume_rejects_a_rebuilt_zip_that_does_not_match(monkeypatch, tmp_path):
    module = load()
    loc = _locations(tmp_path)
    loc['manifest'].write_text('existing manifest\n')
    parent = _Manifest(zip_sha256='expected')
    existing = _Manifest(zip_sha256='expected')
    built = {'manifest': existing, 'build_calls': 0}
    writes = []
    _bind(monkeypatch, module, loc, parent, built, writes, [])
    monkeypatch.setattr(module, 'sha256_file', lambda path: 'different')
    with pytest.raises(ValueError, match='rebuilt'):
        module.main([])
    assert built['build_calls'] == 1
    assert 'pipeline_args' not in built
    assert writes == []
    assert not loc['pipeline'].exists()


def test_resume_rejects_a_conflicting_generator_commit(monkeypatch, tmp_path):
    module = load()
    loc = _locations(tmp_path)
    loc['manifest'].write_text('existing manifest\n')
    loc['zip'].parent.mkdir(parents=True)
    loc['zip'].write_bytes(b'already')
    parent = _Manifest()
    existing = _Manifest(generator_commit='a' * 40)
    built = {'manifest': existing, 'build_calls': 0}
    writes = []
    _bind(monkeypatch, module, loc, parent, built, writes, [])
    with pytest.raises(ValueError, match='refusing to report success'):
        module.main(['--generator-commit', 'd' * 40])
    assert 'pipeline_args' not in built
    assert built['build_calls'] == 0
    assert writes == []


def test_empty_gate_result_does_not_overwrite_pipeline_evidence(monkeypatch, tmp_path, capsys):
    module = load()
    loc = _locations(tmp_path)
    loc['manifest'].write_text('existing manifest\n')
    loc['zip'].parent.mkdir(parents=True)
    loc['zip'].write_bytes(b'already')
    original = '{"gates":[{"gate":"G5","status":"PASS","reason":""}],"seconds":165.76}\n'
    loc['pipeline'].write_text(original)
    parent = _Manifest()
    existing = _Manifest()
    built = {'manifest': existing, 'build_calls': 0}
    _bind(monkeypatch, module, loc, parent, built, [], [])
    module.main([])
    assert loc['pipeline'].read_text() == original
    printed = json.loads(capsys.readouterr().out)
    assert printed['gates'][0]['gate'] == 'G5'
    assert printed['preserved_pipeline'] is True
