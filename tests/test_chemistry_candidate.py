"""The shipping generator must consume only its declared, hash-pinned factor."""
import numpy as np
import pytest

from tasks.dfthcsos import shipping
from tasks.dfthcsos.generate import sha256_file


def test_changed_factor_fails_before_output(tmp_path):
    source = tmp_path / shipping.INPUT_PATH
    source.parent.mkdir(parents=True)
    source.write_bytes(b'wrong factor')
    with pytest.raises(ValueError, match='SHA-256'):
        shipping.generate(tmp_path / 'out', data=tmp_path, batch_size=10)
    assert not (tmp_path / 'out').exists()


def test_declared_input_rebuild_is_identical_and_keeps_words(tmp_path, monkeypatch):
    source = tmp_path / 'staged' / shipping.INPUT_PATH
    source.parent.mkdir(parents=True)
    words = np.array([[0, 2047, 1024], [1, 33, 129], [2, 44, 512]])
    np.savez(source, angle_words=words)
    monkeypatch.setattr(shipping, 'INPUT_SHA256', sha256_file(source))
    reports = [shipping.generate(tmp_path / name, data=tmp_path / 'staged', batch_size=2)
               for name in ('first', 'second')]
    assert reports[0] == reports[1]
    assert (tmp_path / 'first/dfthcsos/submission.npz').read_bytes() == source.read_bytes()
    from dfthcsos.scoreinfra.circuits import load_circuits, recover_words_from_circuits
    circuits = load_circuits(tmp_path / 'first/dfthcsos')
    recovered, _, _ = recover_words_from_circuits(
        circuits, num_vectors=3, num_angles=3, seed=247)
    np.testing.assert_array_equal(recovered, words)
    assert reports[0]['brot'] == reports[0]['source_brot'] == 11


def test_missing_declared_factor_has_no_reference_fallback(tmp_path):
    with pytest.raises(FileNotFoundError):
        shipping.generate(tmp_path / 'out', data=tmp_path, batch_size=10)
    assert not (tmp_path / 'out').exists()


def test_shipping_config_pins_factor_precision_batch_and_full_shots():
    from ledger.gates.runner import load_config
    config = load_config()
    assert config.inputs['dfthcsos'] == [
        {'path': str(shipping.INPUT_PATH), 'sha256': shipping.INPUT_SHA256}]
    assert config.generators['dfthcsos'] == [
        '{python}', '-m', 'tasks.dfthcsos.shipping', '--out', '{out}', '--batch-size', '10']
    assert config.generators['dqi'][1] == 'tasks/dqi/generate_jfraction.py'
    assert config.spec('G3').params['expected_shots'] == {
        'invsqrt': 200540928, 'dqi': 102400, 'dfthcsos': 572 * 64}


@pytest.mark.parametrize('ratio,expected', [(3.799, 'FAIL'), (3.8, 'PASS'), (4.149, 'PASS')])
def test_chemistry_floor_is_required_even_when_total_score_improves(monkeypatch, ratio, expected):
    from types import SimpleNamespace
    from ledger.gates import checks
    from tasks.dfthcsos.gates import g4_chemistry_floor
    monkeypatch.setattr(checks, 'g4_strict_improvement', lambda _: {'status': 'PASS'})
    ctx = SimpleNamespace(manifest=SimpleNamespace(tasks={
        'dfthcsos': SimpleNamespace(ratio=ratio)}))
    assert g4_chemistry_floor(ctx)['status'].startswith(expected)


def test_chemistry_floor_does_not_override_archive_failure(monkeypatch):
    from ledger.gates import checks
    from tasks.dfthcsos.gates import g4_chemistry_floor
    failure = {'status': 'FAIL: does not beat archive'}
    monkeypatch.setattr(checks, 'g4_strict_improvement', lambda _: failure)
    assert g4_chemistry_floor(None) == failure
