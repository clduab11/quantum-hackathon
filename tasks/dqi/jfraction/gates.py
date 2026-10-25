# SPDX-License-Identifier: Apache-2.0
"""Small exact checks for the paired decoder's replacement arithmetic."""
import kickmix as km

from .mc4_inverse import builder_class
from .norm_recycle_inverse import init_norm_recycle_inverse
from .projection import ProjectionPlan
from .smallspace_inverse import clear_inverse_hmr


def arithmetic_smoke():
    checked = 0
    for value in (0, 1, 2, 3, 7, 8, 63, 64, 255, 4095):
        builder = builder_class()()
        word = builder.create_quantum_register(12, name='input')
        for bit in range(12):
            if value >> bit & 1:
                builder.x(word[bit])
        field = km.GF2Field(12)
        output = init_norm_recycle_inverse(builder, word, field=field)
        # Copy out the classical value before HMR cleanup, without disturbing
        # the input basis state. Check the full compute/erase phase as well.
        witness = builder.create_quantum_register(12, name='witness')
        builder.cx(output, witness)
        clear_inverse_hmr(builder, word, output, field=field)
        circuit = builder.finish_circuit()
        sim = km.Simulator(batch_size=8, seed=236, debug_print=False)
        sim.use_same_registers_as(circuit)
        sim.do(circuit)
        expected = field.div(1, value) if value else 0
        for register, result in ((word, value), (witness, expected), (output, 0)):
            bits = sim.read_across_shots(register)
            for bit in range(len(register)):
                if not (bits[bit] == bool(result >> bit & 1)).all():
                    raise AssertionError(f'inverse/cleanup mismatch for {value}')
        if sim.read_phase_flipped_across_shots().any():
            raise AssertionError(f'inverse cleanup phase for {value}')
        checked += 8
    return checked


def g1_smoke(submission_dir):
    del submission_dir
    try:
        plan = ProjectionPlan(km.GF2Field(3), 2)
        masks = [1, 6, 2, 3, 4, 5, 0]
        if plan.residual(masks)[:2] != [0, 0]:
            raise AssertionError('projection interpolation failed')
        shots = arithmetic_smoke()
    except Exception as error:
        return {'status': f'FAIL: {error}'}
    return {'status': 'PASS', 'inverse_cleanup_shots': shots,
            'projection': 'GF8 two-point interpolation', 'parity': False}
