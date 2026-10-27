"""The floor candidate binds its proxies and G5 output to the public port."""
import hashlib
import importlib
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_config_changes_only_invsqrt():
    base = yaml.safe_load((ROOT / 'configs/gates/pra280-rustad.yaml').read_text())
    for gate in base['gates']:
        if gate['id'] in ('G1', 'G2'):
            hook = gate['params']['hooks']['invsqrt']
            gate['params']['hooks']['invsqrt'] = hook.replace('invsqrt.gates', 'invsqrt.public_port.gates')
    base['generators']['invsqrt'] = ['{python}', '-m', 'tasks.invsqrt.public_port.generate',
                                     '--out', '{out}', '--circuit-only']
    assert yaml.safe_load((ROOT / 'configs/gates/pra281-invsqrt-port.yaml').read_text()) == base


@pytest.mark.parametrize('circuit_only', [True, False])
def test_circuit_only_still_fits_and_builds(monkeypatch, tmp_path, circuit_only):
    from tasks.invsqrt.public_port import fit, generate

    fitted = object()
    monkeypatch.setattr(fit, 'fit_tables', lambda: fitted)
    def build(value):
        assert value is fitted
        return b'fresh circuit', {'sha256': 'test', 'tables': {}}
    monkeypatch.setattr(generate, 'build_from_fit', build)
    monkeypatch.setattr(sys, 'argv', ['generate', '--out', str(tmp_path)]
                        + (['--circuit-only'] if circuit_only else []))
    generate.main()
    expected = {'invsqrt.kmb'} if circuit_only else {'invsqrt.kmb', 'build-report.json'}
    assert {p.name for p in tmp_path.iterdir()} == expected
    assert (tmp_path / 'invsqrt.kmb').read_bytes() == b'fresh circuit'


@pytest.fixture
def gates():
    pytest.importorskip('kickmix')
    return importlib.import_module('tasks.invsqrt.public_port.gates')


@pytest.mark.parametrize('hook', ['g1_smoke', 'g2_proxy'])
def test_missing_and_changed_bytes_fail_before_parsing(gates, tmp_path, hook):
    assert getattr(gates, hook)(tmp_path)['status'].startswith('FAIL:')
    (tmp_path / 'invsqrt.kmb').write_bytes(b'not the selected port')
    result = getattr(gates, hook)(tmp_path)
    assert result['status'].startswith('FAIL:')
    assert result['sha256'] == hashlib.sha256(b'not the selected port').hexdigest()


def test_g2_simulates_the_submitted_circuit_and_propagates_failure(gates, monkeypatch, tmp_path):
    from invsqrt import verify_submission_invsqrt as verifier

    circuit = object()
    monkeypatch.setattr(gates, 'g1_smoke', lambda path: {'status': 'PASS'})
    monkeypatch.setattr(gates.km.Circuit, 'from_file', lambda path: circuit)
    def fail(actual, spec, **kwargs):
        assert actual is circuit
        assert spec.width == 22 and spec.num_shots == 1536
        assert kwargs == {'salt': gates.SALT, 'max_workers': 1}
        raise AssertionError('x was not restored.')
    monkeypatch.setattr(verifier, 'verify', fail)
    result = gates.g2_proxy(tmp_path)
    assert result['status'] == 'FAIL: x was not restored.'
    assert result['parity'] is False
