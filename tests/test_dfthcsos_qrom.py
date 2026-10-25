"""PRA-232: XOR oracles must work on dirty targets and clean their phase/workspace."""
import numpy as np
import pytest

from tasks.dfthcsos.qrom import build_qrom, mobius, quantize_words


@pytest.mark.parametrize('rows', [2, 3, 7, 16, 35, 67])
@pytest.mark.parametrize('bank_bits', [0, 1, 2])
def test_oracle_all_addresses_dirty_targets(rows, bank_bits):
    import kickmix as km
    from dfthcsos.scoreinfra.circuits import register_layout, _check_state
    rng = np.random.default_rng(232)
    table = rng.integers(0, 32, size=(rows, 2), dtype=np.int64)
    circuit, report = build_qrom(table, 5, bank_bits=bank_bits, scratch=6)
    layout = register_layout([circuit])
    addresses = np.tile(np.arange(rows), 64)
    bits = ((addresses[None, :] >> np.arange(len(layout.selection))[:, None]) & 1).astype(bool)
    dirty = rng.integers(0, 32, size=(len(addresses), 2), dtype=np.int64)
    sim = km.Simulator(batch_size=len(addresses), seed=232, counting_operations=True)
    sim.use_same_registers_as(circuit)
    sim.write_across_shots(layout.selection, bits)
    for j, word in enumerate(layout.words):
        sim.write_across_shots(word, ((dirty[:, j][None, :] >> np.arange(5)[:, None]) & 1).astype(bool))
    sim.do(circuit)
    _check_state(sim, circuit, layout, bits, 'PRA-232 dirty targets')
    actual = np.stack([(1 << np.arange(5)) @ sim.read_across_shots(w).astype(np.int64) for w in layout.words], axis=1)
    np.testing.assert_array_equal(actual, dirty ^ table[addresses])
    assert report['num_qubits'] <= 128
    assert sim.operation_statistics().num_toffoli_like / len(addresses) == report['toffoli_per_call']
    sim.do(circuit)
    _check_state(sim, circuit, layout, bits, 'PRA-232 inverse')
    for j, w in enumerate(layout.words):
        np.testing.assert_array_equal((1 << np.arange(5)) @ sim.read_across_shots(w).astype(np.int64), dirty[:, j])


def test_six_wire_pebbling_non_power_of_two():
    # Ten address bits force a six-wire traversal to erase and restore ancestors.
    table = np.arange(997, dtype=np.int64)[:, None] % 4096
    circuit, report = build_qrom(table, 12, bank_bits=0, scratch=6)
    assert report['recomputed_ands'] > 0
    from dfthcsos.scoreinfra.circuits import recover_words_from_circuits
    words, _, _ = recover_words_from_circuits([circuit], num_vectors=997, num_angles=1, seed=232)
    np.testing.assert_array_equal(words, table)


def test_mobius_and_quantization_contract():
    assert mobius(mobius([1, 2, 4, 8])) == [1, 2, 4, 8]
    np.testing.assert_array_equal(quantize_words(np.array([[4095, 6, 10]]), 12, 10), [[0, 2, 2]])
    with pytest.raises(ValueError):
        mobius([1, 2, 3])


@pytest.mark.parametrize('table,brot,options', [
    ([[1.5], [2]], 4, {}), ([[16], [0]], 4, {}),
    ([[1], [0]], 4, {'bank_bits': 3}), ([[1], [0]], 4, {'scratch': 0}),
    (np.ones((16, 12), dtype=np.int64), 12, {}),
])
def test_reject_invalid_or_oversized(table, brot, options):
    with pytest.raises(ValueError):
        build_qrom(table, brot, **options)


def test_parameterized_generator_determinism_and_output_guard(tmp_path):
    from tasks.dfthcsos.circuit import generate
    source = tmp_path / 'factor.npz'
    np.savez(source, angle_words=np.array([[0, 5, 31], [7, 15, 3], [2, 9, 12]]), W=np.ones((1, 1, 1)))
    reports = [generate(tmp_path / name, factorization=source, source_brot=5,
                        brot=4, batch_size=2, bank_bits=1) for name in ('a', 'b')]
    assert reports[0] == reports[1]
    with np.load(tmp_path / 'a/dfthcsos/submission.npz') as actual:
        np.testing.assert_array_equal(actual['W'], np.ones((1, 1, 1)))
        np.testing.assert_array_equal(actual['angle_words'], quantize_words(np.array([[0, 5, 31], [7, 15, 3], [2, 9, 12]]), 5, 4))
    with pytest.raises(ValueError, match='must be empty'):
        generate(tmp_path / 'a', factorization=source, source_brot=5, brot=4, batch_size=2)


def test_g2_uses_circuit_precision_and_cost(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import dfthcsos.verify as verifier
    from tasks.dfthcsos.circuit import generate
    from tasks.dfthcsos.gates import g2_proxy
    source = tmp_path / 'factor.npz'
    np.savez(source, angle_words=np.array([[0, 5, 31], [7, 15, 3], [2, 9, 12]]))
    out = tmp_path / 'out'
    generate(out, factorization=source, source_brot=5, brot=4, batch_size=2)
    monkeypatch.setattr(verifier, 'load_inputs', lambda _: SimpleNamespace(w=np.ones((1, 1, 1)), num_orbitals=4))
    monkeypatch.setattr(verifier, 'load_tree_edges', lambda *args: None)
    def evaluate(inputs, words, edges, brot):
        assert brot == 4
        return dict(error_1=0, error_2=0, Lambda=50, E_gap=4, lambda_eff=20)
    monkeypatch.setattr(verifier, 'evaluate_words', evaluate)
    result = g2_proxy(out)
    assert result['status'] == 'PASS'
    assert result['brot'] == 4
    assert result['estimated_cost'] == 20 * result['estimated_toffoli'] * result['estimated_qubits']
