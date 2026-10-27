"""Storage identities must restore data and every measurement phase."""
import numpy as np
import pytest

from tasks.invsqrt.public_port.storage import relation


def test_relation_rejects_sample_only_match():
    full = np.array([255, 255], dtype=np.uint64)
    a = np.array([85, 85], dtype=np.uint64)
    b = np.array([51, 51], dtype=np.uint64)
    assert relation(a ^ b, {1: a, 2: b}, full, [0], products=False) == ([1, 2], False, None)
    wrong = a ^ b
    wrong[1] ^= np.uint64(1)
    assert relation(wrong, {1: a, 2: b}, full, [0], products=True) is None


def test_quadratic_relation_and_deferred_measurement_phase():
    full = np.array([255], dtype=np.uint64)
    a = np.array([170], dtype=np.uint64)
    b = np.array([204], dtype=np.uint64)
    c = np.array([240], dtype=np.uint64)
    target = (a & b) ^ c ^ full
    terms, constant, product = relation(target, {1: a, 2: b, 3: c}, full, [0])
    values = {1: a, 2: b, 3: c}
    restored = full.copy() if constant else np.zeros_like(full)
    for q in terms:
        restored ^= values[q]
    restored ^= values[product[0]] & values[product[1]]
    np.testing.assert_array_equal(target, restored)
    for outcome in (0, 1):
        # X-basis erasure contributes m*f; Z on restored f contributes m*f.
        np.testing.assert_array_equal((target ^ restored)*outcome, np.zeros_like(full))


@pytest.mark.parametrize('future', [False, True])
def test_parked_circuit_restores_inputs_scratch_and_random_measurement_phase(future):
    km = pytest.importorskip('kickmix')
    from tasks.invsqrt.public_port.storage import compile_circuit

    b = km.CircuitBuilder()
    x = b.create_quantum_register(22, name='x')
    target = b.alloc_qubits(1)[0]
    b.init_and(x[0], x[1], target)
    scratch = b.alloc_qubits(1)[0]
    b.cx(x[2], scratch)
    for i in range(3, 15):
        b.cx(x[i], scratch)
    if future:
        b.cx(x[0], x[1])
    for i in reversed(range(3, 15)):
        b.cx(x[i], scratch)
    b.cx(x[2], scratch)
    b.free(scratch)
    b.z_pow(target, 0.25)
    if future:
        b.cx(x[0], x[1])
    b.del_and(x[0], x[1], target)
    b.free(target)
    raw = b.finish_circuit()
    compiled, events = compile_circuit(raw, cap=23, future=future)
    assert any(event['product'] is not None for event in events)
    if future:
        assert any(event['deferred'] for event in events)
    reduced = km.Circuit(compiled.text)
    xs = np.tile(np.arange(1, 257, dtype=np.uint64), 8)
    phases = []
    for circuit in (raw, reduced):
        sim = km.Simulator(batch_size=len(xs))
        sim.clear_for_shot()
        sim.write_across_shots(circuit.register_data['x'],
                         ((xs[None, :] >> np.arange(22, dtype=np.uint64)[:, None]) & 1).astype(bool))
        sim.do(circuit)
        actual = sim.read_across_shots(circuit.register_data['x'])
        expected = ((xs[None, :] >> np.arange(22, dtype=np.uint64)[:, None]) & 1).astype(bool)
        np.testing.assert_array_equal(actual, expected)
        scratch = km.array([km.q(i) for i in range(22, circuit.num_qubits)])
        assert not sim.read_across_shots(scratch).any()
        phases.append([sim.read_shot_phase(i) for i in range(len(xs))])
    np.testing.assert_array_equal(phases[0], phases[1])
