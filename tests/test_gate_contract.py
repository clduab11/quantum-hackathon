"""Exercise the module:function handoff consumed by the ledger gate runner."""
import importlib

import pytest

from harness import score_local
from harness.archive import unpack
from harness.runtime import LOCAL_SALT
from ledger.gates.g0_preflight import preflight
from test_g0 import archive


def resolve(hook):
    module, function = hook.split(':')
    return getattr(importlib.import_module(module), function)


@pytest.mark.parametrize('bad', [False, True])
def test_runner_dispatch_stops_at_failed_g0(tmp_path, monkeypatch, bad):
    import kickmix
    def forbidden(*args, **kwargs):
        pytest.fail('G0 attempted simulation')
    monkeypatch.setattr(kickmix, 'Simulator', forbidden)
    calls = []
    def g3(path, **kwargs):
        calls.append(kwargs)
        return {'status': 'PASS'}
    monkeypatch.setattr(score_local, 'score_submission', g3)
    with unpack(archive(tmp_path, instruction='INVALID q0\n' if bad else '')) as root:
        result = resolve('ledger.gates.g0_preflight:preflight')(root)
        if result['status'] == 'PASS':
            result = resolve('harness.score_local:score_submission')(root, salt_label=LOCAL_SALT)
    assert result['status'].startswith('FAIL: ') if bad else result['status'] == 'PASS'
    assert calls == ([] if bad else [{'salt_label': LOCAL_SALT}])


def test_g3_independently_rejects_bad_input_before_baseline_or_verification(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Bad input reached baseline or verifier')
    monkeypatch.setattr(score_local, 'verify_all', forbidden)
    monkeypatch.setattr(score_local, 'load_baseline', forbidden)
    with unpack(archive(tmp_path, oversized=True)) as root:
        assert score_local.score_submission(root, salt_label=LOCAL_SALT)['status'].startswith('FAIL: ')


@pytest.mark.parametrize('options', [{'salt_label': 'other'}, {'salt_label': LOCAL_SALT, 'shot_divisor': 2}])
def test_g3_refuses_changed_salt_or_shots(tmp_path, monkeypatch, options):
    monkeypatch.setattr(score_local, 'parse_submission', lambda *a: pytest.fail('Unsupported verifier mode parsed input'))
    assert score_local.score_submission(tmp_path, **options)['status'].startswith('FAIL: ')


def test_g3_preserves_verifier_summary_and_aggregates(tmp_path, monkeypatch):
    inv = {'status': 'PASS', 'num_qubits': 2, 'toffoli_count': 3,
           't_count': 1, 'rotation_count': 0, 'score': 6.5}
    dqi = {'status': 'PASS', 'num_qubits': 2, 'toffoli_count': 3,
           'repetition_factor': 1.2, 'score': 14.4}
    df = {'status': 'PASS', 'num_qubits': 730, 'toffoli_count': 93237,
          'metrics': {'Lambda': 308.4559397330944, 'E_gap': 3.965477244291833},
          'score': 3355599588.3155365}
    summaries = {'invsqrt': inv, 'dqi': dqi, 'dfthcsos': df}
    baselines = {name: row['score'] for name, row in summaries.items()}
    monkeypatch.setattr(score_local, 'load_baseline', lambda _: baselines)
    monkeypatch.setattr(score_local, 'verify_all', lambda _: ((n, r, 1.) for n, r in summaries.items()))
    with unpack(archive(tmp_path)) as root:
        result = score_local.score_submission(root, salt_label=LOCAL_SALT)
    assert result['status'] == 'PASS'
    assert result['tasks'] == summaries
    assert result['tasks']['invsqrt'] is inv
    assert result['geometric_mean'] == 1.
    assert result['baseline_costs'] == baselines
    assert len(result['kickmix_build_id']) == 64
    assert result['qualtran_pin'] is None
    assert set(result['verifier_hashes']) == set(summaries)
