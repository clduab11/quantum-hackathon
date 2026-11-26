"""Identity guards of the hermes-syed-v12 candidate runner (no circuits are loaded, no gate runs)."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'ledger/evidence/hermes-syed-v12/run_candidate.py'
DQI_SHA256 = '7cbe8ecf6f6e9743529b574f019504bb1712ce06fbb570c719ce9d9e2c914cd9'


def load():
    spec = importlib.util.spec_from_file_location('hermes_syed_v12_run_candidate', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refuses_a_zip_that_is_not_the_built_candidate(tmp_path):
    run = load()
    other = tmp_path / 'other.zip'
    other.write_bytes(b'not the candidate')
    with pytest.raises(ValueError, match='expected the built candidate'):
        run.check_zip(other)


def test_refuses_uncommitted_candidate_paths(monkeypatch):
    run = load()
    calls = []

    def fake(argv, **kwargs):
        calls.append(argv)
        return '?? tasks/public_portfolio/generate.py\n'

    monkeypatch.setattr(run.subprocess, 'check_output', fake)
    with pytest.raises(ValueError, match='commit the candidate'):
        run.check_committed()
    assert calls[0][:4] == ['git', 'status', '--porcelain', '--']
    assert 'tasks/public_portfolio' in calls[0]
    assert 'configs/gates/hermes-syed-v12.yaml' in calls[0]
    # Gate evidence lands beside the runner; it must not make a resumed run look uncommitted.
    assert 'ledger/evidence/hermes-syed-v12' not in calls[0]
    assert 'ledger/evidence/hermes-syed-v12/run_candidate.py' in calls[0]


def test_returns_head_when_candidate_paths_are_clean(monkeypatch):
    run = load()
    outputs = iter(['', 'a' * 40 + '\n'])
    monkeypatch.setattr(run.subprocess, 'check_output', lambda argv, **kwargs: next(outputs))
    assert run.check_committed() == 'a' * 40


def test_pins_cover_every_task_and_a_mismatch_is_refused():
    run = load()
    expected = run.pinned_files()
    assert sorted(expected) == ['dfthcsos', 'dqi', 'invsqrt']
    assert len(expected['dfthcsos']) == 16
    assert expected['dqi'] == {'dqi.kmb': DQI_SHA256}
    manifest = SimpleNamespace(tasks={t: SimpleNamespace(files=dict(f)) for t, f in expected.items()})
    run.check_pins(manifest)
    manifest.tasks['invsqrt'].files = {'invsqrt.kmb': '0' * 64}
    with pytest.raises(ValueError, match='invsqrt'):
        run.check_pins(manifest)


def test_every_task_names_the_pinned_licence_and_source():
    run = load()
    provenance = run.provenance()
    assert set(provenance) == {'invsqrt', 'dqi', 'dfthcsos'}
    for record in provenance.values():
        assert record.licence == 'Apache-2.0'
        assert record.parent_url.endswith('/vqcc-own-circuit-portfolio/versions/12')
        assert 'not certified' in record.notes


def test_g5_stages_declared_inputs_from_the_selected_package_root(monkeypatch, tmp_path):
    import ledger.gates.runner as runner
    import ledger.run_manifest as run_manifest

    run = load()
    seen = {}
    manifest = SimpleNamespace(generator_commit='a' * 40, zip_sha256=run.ZIP_SHA256, gates=[],
                               geometric_mean=None, shipping_problems=lambda: ['not gated'])
    monkeypatch.setattr(run, 'check_zip', lambda path: tmp_path / 'c.zip')
    monkeypatch.setattr(run, 'check_committed', lambda: 'a' * 40)
    monkeypatch.setattr(run, 'check_pins', lambda m: None)
    monkeypatch.setattr(run_manifest, 'MANIFESTS_DIR', tmp_path)
    monkeypatch.setattr(runner, 'start_candidate', lambda *a, **k: manifest)
    monkeypatch.setattr(runner, 'load_config', lambda path: 'config')
    monkeypatch.setattr(run_manifest, 'write_manifest', lambda m, p, exclusive: tmp_path / 'm.json')
    monkeypatch.setattr(run_manifest, 'manifest_path', lambda m: tmp_path / 'm.json')
    monkeypatch.setattr(run_manifest, 'read_manifest', lambda p: manifest)

    def fake_pipeline(m, zip_path, config, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(runner, 'run_pipeline', fake_pipeline)
    assert run.main(['--package-root', str(tmp_path / 'pkg'), '--stop-after', 'G2']) == 1
    assert seen['package_root'] == tmp_path / 'pkg'
    assert seen['stop_after'] == 'G2'
