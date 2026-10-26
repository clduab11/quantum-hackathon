"""Independent arithmetic and phase checks for the submission-9 port."""
import numpy as np
import pytest
import kickmix as km

from tasks.dqi.jfraction.mc4_inverse import builder_class


def bits(values):
    return ((np.asarray(values, dtype=np.uint16)[None, :] >>
             np.arange(12, dtype=np.uint16)[:, None]) & 1).astype(bool)


def test_gold_cube_complete_domain_preserves_source_target_and_phase():
    from tasks.dqi.hankel.gold_cube import xor_cube
    b = builder_class()()
    source = b.create_quantum_register(12, name='source')
    target = b.create_quantum_register(12, name='target')
    xor_cube(b.native, source, target)
    circuit = b.finish_circuit()
    x = np.arange(4096, dtype=np.uint16)
    y = x ^ 0xA5B
    gf = km.GF2Field(12)
    expected = y ^ np.array([gf.pow(int(v), 3) for v in x], dtype=np.uint16)
    sim = km.Simulator(batch_size=4096, seed=250)
    sim.use_same_registers_as(circuit)
    sim.write_across_shots(source, bits(x))
    sim.write_across_shots(target, bits(y))
    sim.do(circuit)
    assert np.array_equal(sim.read_across_shots(source), bits(x))
    assert np.array_equal(sim.read_across_shots(target), bits(expected))
    assert not sim.read_phase_flipped_across_shots().any()
    assert circuit.num_qubits == 24
    assert circuit.operation_statistics().num_toffoli_like == 26


def test_extraction_hooks_restore_fallback_even_on_exception():
    from tasks.dqi.hankel.cyclic_gold import installed
    from tasks.dqi.jfraction import jfraction_decoder, quadratic_cube
    before = (jfraction_decoder.shear, quadratic_cube.xor_cube)
    with pytest.raises(RuntimeError, match='fixture'):
        with installed():
            assert jfraction_decoder.shear is not before[0]
            raise RuntimeError('fixture')
    assert (jfraction_decoder.shear, quadratic_cube.xor_cube) == before


def test_hankel_phase_matches_forney_formula_and_restores_polynomials():
    from tasks.dqi.hankel.hankel_half import forney
    gf = km.GF2Field(12)
    b = builder_class()()
    numerator = [b.create_quantum_register(12, name=f'o{i}') for i in range(5)]
    denominator = [b.create_quantum_register(12, name=f's{i}') for i in range(5)]
    masks = [b.create_classical_register(12, name=f'm{i}') for i in range(8)]
    forney(b, numerator, denominator, masks, field=gf)
    circuit = b.finish_circuit()
    shots = 64
    rng = np.random.default_rng(250)
    values = np.zeros((10, shots), dtype=np.uint16)
    measured = rng.integers(0, 4096, size=(8, shots), dtype=np.uint16)
    phases = np.zeros(shots, dtype=bool)

    def evaluate(poly, x):
        result = 0
        for coefficient in reversed(poly):
            result = gf.mul(result, x) ^ int(coefficient)
        return result

    for shot in range(shots):
        # Distinct fixed locations: degree 0..5 exercises terminal zero pivots.
        weight = shot % 6
        locations = list(range(weight))
        sigma = [1]
        for j in locations:
            factor = gf.pow(gf.primitive_element, j)
            product = [0] * (len(sigma) + 1)
            for k, coefficient in enumerate(sigma):
                product[k] ^= coefficient
                product[k + 1] ^= gf.mul(coefficient, factor)
            sigma = product
        omega = [int(v) for v in rng.integers(0, 4096, size=weight)]
        values[:weight, shot] = omega
        values[5:5 + weight, shot] = sigma[1:]
        derivative = [sigma[k] if k % 2 else 0 for k in range(1, len(sigma))]
        phase = 0
        for j in locations:
            root = gf.pow(gf.primitive_element, -j % 4095)
            quotient = gf.div(evaluate(omega, root), evaluate(derivative, root))
            phase ^= (quotient & int(measured[j, shot])).bit_count() & 1
        phases[shot] = bool(phase)
    sim = km.Simulator(batch_size=shots, seed=250)
    sim.use_same_registers_as(circuit)
    for word, data in zip(numerator + denominator, values):
        sim.write_across_shots(word, bits(data))
    for word, data in zip(masks, measured):
        sim.write_across_shots(word, bits(data))
    sim.do(circuit)
    for word, data in zip(numerator + denominator, values):
        assert np.array_equal(sim.read_across_shots(word), bits(data))
    assert np.array_equal(sim.read_phase_flipped_across_shots(), phases)


def test_hankel_gate_checks_new_arithmetic():
    from tasks.dqi.hankel.gates import g1_smoke
    report = g1_smoke(None)
    assert report['status'] == 'PASS', report
    assert report['cube_complete_domain'] == 4096


def test_port_source_pins():
    import hashlib
    import json
    from pathlib import Path
    port = Path(__file__).resolve().parents[1] / 'tasks/dqi/hankel'
    for item in json.loads((port / 'SOURCE_MAP.json').read_text())['files']:
        assert hashlib.sha256((port / item['file']).read_bytes()).hexdigest() == item['port_sha256']
