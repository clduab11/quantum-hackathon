"""PRA-280 paired lookup: dirty targets, phase, padding and input pins."""
import numpy as np
import pytest

from tasks.dfthcsos.paired_qrom import build_qrom


@pytest.mark.parametrize('rows', [64, 67, 1366])
def test_dirty_xor_phase_and_inverse(rows):
    import kickmix as km
    from dfthcsos.scoreinfra.circuits import register_layout, _check_state
    rng = np.random.default_rng(280)
    # Signed-gauge words duplicate bit 6 into bit 7, including XOR deltas.
    table = rng.integers(0, 128, size=(rows, 3), dtype=np.int64)
    table |= (table & 64) << 1
    circuit, report = build_qrom(table, 8)
    layout = register_layout([circuit])
    addresses = np.tile(np.arange(rows), 64)
    selection = ((addresses[None, :] >> np.arange(len(layout.selection))[:, None]) & 1).astype(bool)
    dirty = rng.integers(0, 256, size=(len(addresses), 3), dtype=np.int64)
    sim = km.Simulator(batch_size=len(addresses), seed=280, counting_operations=True)
    sim.use_same_registers_as(circuit)
    sim.write_across_shots(layout.selection, selection)
    for j, word in enumerate(layout.words):
        sim.write_across_shots(word, ((dirty[:, j][None, :] >> np.arange(8)[:, None]) & 1).astype(bool))
    for expected in (dirty ^ table[addresses], dirty):
        sim.do(circuit)
        _check_state(sim, circuit, layout, selection, 'PRA-280 dirty XOR')
        actual = np.stack([(1 << np.arange(8)) @ sim.read_across_shots(w).astype(np.int64)
                           for w in layout.words], axis=1)
        np.testing.assert_array_equal(actual, expected)
    assert report['num_qubits'] <= 128
    assert sim.operation_statistics().num_toffoli_like / len(addresses) == 2 * report['toffoli_per_call']


@pytest.mark.parametrize('table,bits', [
    (np.zeros((64, 4), dtype=np.int64), 8),
    (np.full((64, 3), 128, dtype=np.int64), 8),
    (np.zeros((64, 3)), 8),
    (np.zeros((64, 3), dtype=np.int64), 0),
])
def test_reject_invalid_layout(table, bits):
    with pytest.raises(ValueError):
        build_qrom(table, bits)


def test_gauge_preserves_vectors_up_to_sign():
    from tasks.dfthcsos.projective_gauge import signed_gauge, decode_tree
    edges = np.array([[0, 1], [0, 2], [1, 3]])
    # Exhaust quarter turns, where floating angle reconstruction is ambiguous.
    words = np.array(np.meshgrid(*([np.arange(0, 256, 32)] * 3))).reshape(3, -1).T
    gauged, signs = signed_gauge(words, edges, 8)
    np.testing.assert_allclose(decode_tree(gauged, edges, 8),
                               signs[:, None] * decode_tree(words, edges, 8), atol=1e-14)
    assert not np.any(((gauged >> 7) ^ (gauged >> 6)) & 1)


def test_input_pin_rejects_before_writes(tmp_path):
    from tasks.dfthcsos import rustad
    source = tmp_path / rustad.INPUT_PATH
    source.parent.mkdir(parents=True)
    source.write_bytes(b'changed input')
    with pytest.raises(ValueError, match='SHA-256'):
        rustad.generate(tmp_path / 'out', data=tmp_path)
    assert not (tmp_path / 'out').exists()


def test_generator_dry_run_determinism_and_guard(tmp_path, monkeypatch):
    from tasks.dfthcsos import rustad
    from tasks.dfthcsos.generate import sha256_file
    from tasks.dfthcsos.projective_gauge import signed_gauge
    from dfthcsos.scoreinfra.circuits import load_circuits, recover_words_from_circuits
    source = tmp_path / rustad.INPUT_PATH
    source.parent.mkdir(parents=True)
    words = np.random.default_rng(280).integers(0, 256, (67, 4), dtype=np.int64)
    edges = np.array([[0, 1], [0, 2], [1, 3], [2, 4]])
    np.savez(source, angle_words=words, tree_edges=edges)
    monkeypatch.setattr(rustad, 'INPUT_SHA256', sha256_file(source))
    rustad.generate(tmp_path / 'dry', data=tmp_path, dry_run=True)
    assert not (tmp_path / 'dry').exists()
    first = rustad.generate(tmp_path / 'first', data=tmp_path)
    second = rustad.generate(tmp_path / 'second', data=tmp_path)
    assert first == second
    assert (tmp_path / 'first/dfthcsos/submission.npz').read_bytes() == source.read_bytes()
    actual, _, _ = recover_words_from_circuits(load_circuits(tmp_path / 'first/dfthcsos'),
                                              num_vectors=67, num_angles=4, seed=280)
    np.testing.assert_array_equal(actual, signed_gauge(words, edges, 8)[0])
    with pytest.raises(ValueError, match='must be empty'):
        rustad.generate(tmp_path / 'first', data=tmp_path)


@pytest.mark.parametrize('ratio,expected', [(7.6789, 'FAIL'), (float('nan'), 'FAIL'),
                                           (None, 'FAIL'), (7.679, 'PASS')])
def test_measured_floor(monkeypatch, ratio, expected):
    from types import SimpleNamespace
    from ledger.gates import checks
    from tasks.dfthcsos.rustad_gates import g4_floor
    monkeypatch.setattr(checks, 'g4_strict_improvement', lambda _: {'status': 'PASS'})
    ctx = SimpleNamespace(manifest=SimpleNamespace(tasks={'dfthcsos': SimpleNamespace(ratio=ratio)}))
    assert g4_floor(ctx)['status'].startswith(expected)


def test_candidate_config_and_compiler_smoke():
    from pathlib import Path
    from ledger.gates.runner import load_config
    from tasks.dfthcsos import rustad
    from tasks.dfthcsos.rustad_gates import g1_smoke
    config = load_config(Path('configs/gates/pra280-rustad.yaml'))
    assert config.inputs['dfthcsos'] == [{'path': str(rustad.INPUT_PATH), 'sha256': rustad.INPUT_SHA256}]
    assert config.spec('G3').params['expected_shots']['dfthcsos'] == 1366 * 64
    assert config.generators['dfthcsos'][2] == 'tasks.dfthcsos.rustad'
    assert all(not spec.waivable for spec in config.gates)
    assert g1_smoke(None)['status'] == 'PASS'
