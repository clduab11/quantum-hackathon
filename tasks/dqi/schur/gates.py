"""Exact Schur arithmetic and reduced-oracle smoke checks."""
import kickmix as km

def check_joint_cover():
    from tasks.dqi.schur.joint_cubic_inverse_product_kernel import joint_data
    from tasks.dqi.schur.cubic_trace_field import data

    terms, cols = joint_data()
    assert len(terms) == 17
    g = km.GF2Field(4)
    k = data()['kappa']
    for x in range(256):
        b, c = x & 15, x >> 4
        expected = g.mul(k, g.mul(b, c)) | (
            (g.mul(k, g.pow(b, 3)) ^ g.mul(g.mul(k, k), g.pow(c, 3))) << 4
        )
        actual = 0
        for j, col in enumerate(cols):
            if x >> j & 1:
                actual ^= col
        for left, right, out in terms:
            if (left & x).bit_count() % 2 and (right & x).bit_count() % 2:
                actual ^= out
        assert actual == expected, x


def check_small_generator(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys
    import numpy as np

    root = Path(__file__).resolve().parents[3]
    subprocess.run([sys.executable, '-m', 'tasks.dqi.generate_schur', '--out', str(tmp_path),
                    '--n', '6', '--m', '7'], cwd=root, check=True,
                   env=dict(os.environ, PYTHONPATH=str(root)), capture_output=True)
    circuit = km.Circuit.from_file(str(tmp_path / 'dqi.kmb'), format='kmb')
    shots = 128
    gf = km.GF2Field(12)
    rng = np.random.default_rng(261)
    masks = rng.integers(0, 4096, (7, shots))
    syndromes = np.zeros((6, shots), dtype=np.uint16)
    phases = np.zeros(shots, dtype=bool)
    for shot in range(shots):
        # Weight zero, one, two, three; fixed positions, no seed selection.
        for position in range(shot % 4):
            value = int(rng.integers(1, 4096))
            for degree in range(6):
                syndromes[degree, shot] ^= gf.mul(value, gf.pow(2, position * (degree + 1)))
            phases[shot] ^= bool((value & int(masks[position, shot])).bit_count() % 2)
    bits = lambda values: ((values[None, :] >> np.arange(12)[:, None]) & 1).astype(bool)
    sim = km.Simulator(batch_size=shots, seed=261)
    sim.use_same_registers_as(circuit)
    for j in range(6):
        sim.write_across_shots(circuit.register_data[f'S{j}'], bits(syndromes[j]))
    for j in range(7):
        sim.write_across_shots(circuit.register_data[f'E{j}'], bits(masks[j]))
    sim.do(circuit)
    for j in range(6):
        assert np.array_equal(sim.read_across_shots(circuit.register_data[f'S{j}']), bits(syndromes[j]))
    for j in range(7):
        assert np.array_equal(sim.read_across_shots(circuit.register_data[f'E{j}']), bits(masks[j]))
    assert not sim.read_across_shots(km.array([km.q(q) for q in range(72, circuit.num_qubits)])).any()
    assert not sim.read_across_shots(km.array([km.b(b) for b in range(84, circuit.num_bits)])).any()
    assert np.array_equal(sim.read_phase_flipped_across_shots(), phases)


def check_inverse_phase():
    import numpy as np
    from tasks.dqi.schur.cubic_mask_phase_compact import phase_inverse

    b = km.CircuitBuilder()
    source = b.create_quantum_register(12, 'source')
    mask = b.create_classical_register(12, 'mask')
    phase_inverse(b, source, mask)
    circuit = b.finish_circuit()
    # Component boundary clears private HMR bits, as the full emitter does.
    circuit = km.Circuit(str(circuit) + '\n' + ''.join(
        f'BIT_STORE0 b{i}\n' for i in range(12, circuit.num_bits)))
    x = np.arange(4096)
    masks = (x * 73 + 11) % 4096
    masks[0] = 0
    gf = km.GF2Field(12)
    expected = np.array([bool((gf.pow(int(v), 4094) & int(w)).bit_count() % 2)
                         for v, w in zip(x, masks)])
    bits = lambda values: ((values[None, :] >> np.arange(12)[:, None]) & 1).astype(bool)
    sim = km.Simulator(batch_size=4096, seed=261)
    sim.use_same_registers_as(circuit)
    sim.write_across_shots(source, bits(x))
    sim.write_across_shots(mask, bits(masks))
    sim.do(circuit)
    assert np.array_equal(sim.read_across_shots(source), bits(x))
    assert np.array_equal(sim.read_across_shots(mask), bits(masks))
    assert np.array_equal(sim.read_phase_flipped_across_shots(), expected)
    assert not sim.read_across_shots(km.array([km.q(i) for i in range(12, circuit.num_qubits)])).any()
    assert not sim.read_across_shots(km.array([km.b(i) for i in range(12, circuit.num_bits)])).any()


def g1_smoke(submission_dir):
    import tempfile
    from pathlib import Path
    try:
        check_joint_cover()
        check_inverse_phase()
        with tempfile.TemporaryDirectory(prefix='schur-smoke-') as scratch:
            check_small_generator(Path(scratch))
    except Exception as error:
        return {'status': f'FAIL: {type(error).__name__}: {error}'}
    return {'status': 'PASS', 'cover_inputs': 256, 'inverse_inputs': 4096,
            'small_phase_shots': 128, 'small_weights': [0, 1, 2, 3]}
