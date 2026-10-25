"""Manwithacat's projection identity, implemented independently via interpolation."""
import random

import kickmix as km
import pytest

from tasks.dqi.jfraction.projection import ProjectionPlan, project_masks


def dot(a, b):
    return sum((x & y).bit_count() for x, y in zip(a, b)) % 2


def syndrome(errors, count, field):
    result = [0] * count
    for j, error in enumerate(errors):
        for i in range(count):
            result[i] ^= field.mul(error, field.pow(field.primitive_element, j * (i + 1)))
    return result


@pytest.mark.parametrize('degree,count', [(3, 2), (4, 6), (12, 70)])
def test_projection_preserves_phase_for_all_error_positions(degree, count):
    field = km.GF2Field(degree)
    plan = ProjectionPlan(field, count)
    length = (1 << degree) - 1
    rng = random.Random(236)
    masks = [rng.randrange(1 << degree) for _ in range(length)]
    remainder = plan.residual(masks)
    assert remainder[:count] == [0] * count
    correction = [plan.parity_mask(x) for x in plan.coefficients(masks[:count])]
    # A linear identity: every position and basis bit spans every possible error vector.
    for j in range(length):
        basis_syndrome = [field.pow(field.primitive_element, (i + 1) * j) for i in range(count)]
        for bit in range(degree):
            s = [field.mul(x, 1 << bit) for x in basis_syndrome]
            assert dot(s, correction) ^ ((remainder[j] >> bit) & 1) == ((masks[j] >> bit) & 1)


def test_projection_emits_correct_phase_and_classical_masks_with_dirty_scratch():
    field = km.GF2Field(3)
    plan = ProjectionPlan(field, 2)
    errors = [3, 0, 7, 0, 1, 2, 0]
    values = syndrome(errors, 2, field)
    for masks in ([0] * 7, [7] * 7, [1, 6, 2, 3, 4, 5, 0]):
        b = km.CircuitBuilder()
        s = [b.create_quantum_register(3, name=f'S{i}') for i in range(2)]
        e = [b.create_classical_register(3, name=f'E{i}') for i in range(7)]
        for word, value in zip(s, values):
            for bit in range(3):
                if value >> bit & 1:
                    b.x(word[bit])
        for word, value in zip(e, masks):
            for bit in range(3):
                b.bit_store(word[bit], bool(value >> bit & 1))
        dirty = b.alloc_bits(300)
        b.bit_store(dirty, True)
        b.free(dirty)
        residual = project_masks(b, s, e, field=field)
        circuit = b.finish_circuit()
        sim = km.Simulator(batch_size=1, seed=236, debug_print=False)
        sim.use_same_registers_as(circuit)
        sim.do(circuit)
        def read(word):
            return sum(int(v) << bit for bit, v in enumerate(sim.read_across_shots(word)[:, 0]))
        got = [read(word) for word in residual]
        assert got == plan.residual(masks)
        assert [read(word) for word in s] == values
        assert [read(word) for word in e] == masks
        assert bool(sim.read_phase_flipped_across_shots()[0]) == bool(dot(errors, masks) ^ dot(errors, got))
        assert circuit.num_qubits == 6
        assert circuit.operation_statistics().num_toffoli_like == 0


def test_projection_rejects_invalid_dimensions():
    with pytest.raises(ValueError):
        ProjectionPlan(km.GF2Field(3), 8)
