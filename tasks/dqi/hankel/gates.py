# SPDX-License-Identifier: Apache-2.0
"""Small exact check of the replacement cube, plus inherited inverse checks."""
import numpy as np
import kickmix as km

from ..jfraction.gates import g1_smoke as fallback_smoke
from ..jfraction.mc4_inverse import builder_class
from .gold_cube import xor_cube


def g1_smoke(submission_dir):
    report = fallback_smoke(submission_dir)
    if report['status'] != 'PASS':
        return report
    try:
        builder = builder_class()()
        source = builder.create_quantum_register(12, name='source')
        target = builder.create_quantum_register(12, name='target')
        xor_cube(builder.native, source, target)
        circuit = builder.finish_circuit()
        values = np.arange(4096, dtype=np.uint16)
        initial = values ^ 0xA5B
        field = km.GF2Field(12)
        expected = initial ^ np.array([field.pow(int(x), 3) for x in values], dtype=np.uint16)

        def bits(x):
            return ((x[None, :] >> np.arange(12, dtype=np.uint16)[:, None]) & 1).astype(bool)

        sim = km.Simulator(batch_size=4096, seed=250)
        sim.use_same_registers_as(circuit)
        sim.write_across_shots(source, bits(values))
        sim.write_across_shots(target, bits(initial))
        sim.do(circuit)
        if not np.array_equal(sim.read_across_shots(source), bits(values)):
            raise AssertionError('cube changed its source')
        if not np.array_equal(sim.read_across_shots(target), bits(expected)):
            raise AssertionError('cube target mismatch')
        if sim.read_phase_flipped_across_shots().any():
            raise AssertionError('cube phase mismatch')
    except Exception as error:
        return {'status': f'FAIL: {error}'}
    return {**report, 'cube_complete_domain': 4096, 'cube_toffolis': 26}
