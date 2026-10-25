# SPDX-License-Identifier: Apache-2.0
# Praxen replacement for notebook runtime wiring. See PROVENANCE.md.
"""Explicit dependency boundary: Kickmix and our committed Google reference source."""
import kickmix as km
from tasks.dqi import reference_circuit as ref


def build(builder, *, iterations=35, decoder_type):
    field = km.GF2Field(12)
    if (field.modulus, field.primitive_element) != (4179, 2):
        raise ValueError('Unexpected DQI field.')
    syndromes = [builder.create_quantum_register(12, name=f'S{i}') for i in range(70)]
    outcomes = [builder.create_classical_register(12, name=f'E{j}') for j in range(4095)]
    decoder_type(70, field).build_syndrome_decoding_mbuc(
        builder, syndromes=syndromes, error_mbuc=outcomes, n_iters=iterations)
    return builder.finish_circuit()
