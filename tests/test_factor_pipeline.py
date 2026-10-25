import numpy as np
import pytest
from scipy.optimize._numdiff import approx_derivative

from tasks.dfthcsos.factor_math import structure_value_grad, compress, packed_target
from tasks.dfthcsos.factor_support import prediction, checked_inputs
from tasks.dfthcsos.factor_offsets import offset_value_grad
from tasks.dfthcsos.factor_support import write_npz, sha256


def test_structure_gradient_matches_independent_finite_difference():
    rng = np.random.default_rng(8)
    u, w = rng.normal(size=(2, 3, 4)), rng.normal(size=(2, 3, 2))
    target = rng.normal(size=(10, 10))
    target = (target + target.T) / 2
    x = np.concatenate([u.ravel(), w.ravel()])
    fun = lambda x: structure_value_grad(x, u.shape, w.shape, target, 0.003)
    value, gradient = fun(x)
    numeric = approx_derivative(lambda x: fun(x)[0], x).ravel()
    assert np.isfinite(value)
    np.testing.assert_allclose(gradient, numeric, rtol=2e-5, atol=2e-6)


def test_packed_target_has_full_tensor_norm():
    rng = np.random.default_rng(4)
    x = rng.normal(size=(2, 4, 4))
    x = (x + x.transpose(0, 2, 1)) / 2
    tei = np.einsum('apq,ars->pqrs', x, x)
    s = np.eye(4)
    target = packed_target(tei, s)
    full = tei + 0.5 * (np.einsum('pq,rs->pqrs', s, s) * 2)
    assert np.linalg.norm(target) == pytest.approx(np.linalg.norm(full))


def test_compression_preserves_fixed_shift_and_rejects_growth():
    rng = np.random.default_rng(2)
    p = dict(U=rng.normal(size=(3, 4, 5)), W=rng.normal(size=(3, 4, 3)),
             H2_I=rng.normal(size=(3, 3)), H1_I=np.array(1.), Hsym_lower=np.zeros(15))
    q = compress(p, 2, 3, 2)
    assert q['U'].shape == (2, 3, 5)
    assert q['W'].shape == (2, 3, 2)
    np.testing.assert_array_equal(q['Hsym_lower'], p['Hsym_lower'])
    with pytest.raises(ValueError, match='shrink'):
        compress(p, 4, 4, 3)


def test_cost_model_includes_angles_and_reproduces_reference():
    h = dict(toffoli=13757, persistent_qubits=90, temporary_qubits=544)
    p = prediction(76, 65, 60, 12, h)
    assert (p['T'], p['Q'], p['angle_qubits']) == (93237, 730, 119)
    assert p['angle_qubits'] <= 128


def test_inputs_fail_closed_on_unpinned_data(tmp_path):
    (tmp_path / 'unexpected.npz').write_bytes(b'not a baseline')
    with pytest.raises((FileNotFoundError, ValueError)):
        checked_inputs(tmp_path)


def test_input_hash_tamper_fails(tmp_path, monkeypatch):
    import json
    import tasks.dfthcsos.factor_support as support
    data = tmp_path/'baseline.npz'
    data.write_bytes(b'approved data')
    pins = tmp_path/'pins.json'
    pins.write_text(json.dumps({'files':[{'path':data.name,'sha256':sha256(data)}]}))
    monkeypatch.setattr(support, 'PIN_FILE', pins)
    assert checked_inputs(tmp_path)['files']
    data.write_bytes(b'unapproved data')
    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        checked_inputs(tmp_path)


def test_offset_gradient_matches_finite_difference():
    rng = np.random.default_rng(12)
    w = rng.normal(size=(2, 3, 2))
    x = rng.normal(size=(2, 2, 4, 4))
    x = (x + x.transpose(0, 1, 3, 2)) / 2
    offsets = rng.normal(size=4)
    fun = lambda d: offset_value_grad(d, x, w, np.eye(4)*30, 4.)
    np.testing.assert_allclose(fun(offsets)[1], approx_derivative(lambda d:fun(d)[0], offsets).ravel(), rtol=2e-5)


def test_npz_is_deterministic_and_never_overwrites(tmp_path):
    arrays = dict(W=np.arange(9).reshape(3,3), brot=np.array(10))
    write_npz(tmp_path/'a.npz', arrays)
    write_npz(tmp_path/'b.npz', dict(reversed(list(arrays.items()))))
    assert sha256(tmp_path/'a.npz') == sha256(tmp_path/'b.npz')
    with pytest.raises(FileExistsError):
        write_npz(tmp_path/'a.npz', arrays)
    with pytest.raises(ValueError, match='nonfinite'):
        write_npz(tmp_path/'bad.npz', dict(W=np.array([np.nan])))
    assert not (tmp_path/'bad.npz').exists()


@pytest.mark.parametrize('bits', [7, 10, 12])
def test_g2_uses_declared_precision_even_for_small_words(tmp_path, monkeypatch, bits):
    import sys
    import types
    from tasks.dfthcsos.checks import proxy_submission
    fake = types.ModuleType('dfthcsos.verify')
    fake.load_inputs = lambda path: types.SimpleNamespace(w=np.zeros((2,3,4)), num_orbitals=5)
    fake.load_tree_edges = lambda *args: np.array([[0,1]])
    def evaluate(inputs, words, edges, brot):
        assert brot == bits
        return dict(error_1=0., error_2=0., Lambda=300., E_gap=4., lambda_eff=49.)
    fake.evaluate_words = evaluate
    fake.heuristic_costs = lambda *args: dict(toffoli=10, qubits=10)
    monkeypatch.setitem(sys.modules, 'dfthcsos.verify', fake)
    np.savez(tmp_path/'submission.npz', angle_words=np.ones((3,2), dtype=np.int64), brot=bits)
    assert proxy_submission(tmp_path)['brot'] == bits
    np.savez(tmp_path/'submission.npz', angle_words=np.array([[1 << bits]]), brot=bits)
    with pytest.raises(ValueError, match='angle_words'):
        proxy_submission(tmp_path)
