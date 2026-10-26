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
