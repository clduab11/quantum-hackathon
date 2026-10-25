# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Experimental exact lifetime changes for the credited SomeJoint decoder.

Uses SomeJoint / Agniv Banerjee's Apache-2.0 finite-field implementation,
without modifying the pinned upstream source or the production wrapper.
No whole-decoder circuit is built by this module.
"""
from __future__ import annotations


def discard_inverse_scaffold(builder, source, scaffold):
    """MBU-erase the norm/inverse scaffold while retaining inverse(source)."""
    basis = builder.bases[12]
    b = builder.native
    assert len(source) == 12 and len(scaffold) == 18
    basis.change_basis(b, source, to_tower=True)
    a, c = source[:6], source[6:]
    norm, reciprocal, chain = scaffold[:6], scaffold[6:12], scaffold[12:]
    builder.del_gf2_inverse_with_scaffold(norm, target=reciprocal,
                                         scaffold=chain, field=basis.inner)
    b.free(reciprocal + chain)
    basis.add_linear(b, a, norm, basis.square_columns)
    basis.add_linear(b, c, norm, basis.delta_square_columns)
    b.del_gf2_mul(a, c, target=norm, field=basis.inner)
    b.free(norm)
    basis.change_basis(b, source, to_tower=False)


def init_compact_inverse(builder, source, *, field):
    inverse, scaffold = builder.init_gf2_inverse_with_scaffold(source, field=field)
    discard_inverse_scaffold(builder, source, scaffold)
    return inverse


def delete_compact_inverse(builder, source, inverse, *, field):
    """Recreate36-Toffoli scaffold, then use the original free MBU deletion."""
    basis = builder.bases[12]
    b = builder.native
    basis.change_basis(b, source, to_tower=True)
    a, c = source[:6], source[6:]
    norm = builder.init_gf2_mul(a, c, field=basis.inner)
    basis.add_linear(b, a, norm, basis.square_columns)
    basis.add_linear(b, c, norm, basis.delta_square_columns)
    reciprocal, chain = builder.init_gf2_inverse_with_scaffold(norm, field=basis.inner)
    basis.change_basis(b, source, to_tower=False)
    scaffold = norm + reciprocal + chain
    builder.del_gf2_inverse_with_scaffold(source, target=inverse,
                                         scaffold=scaffold, field=field)
    b.free(scaffold)


def scale_active_reused_mask(builder, pivot, words, shortened, *, divide):
    """SomeJoint scale_active, sharing its HMR-cleared word with its AND mask.

    The gate sequence is the upstream algorithm with masked=temporary after
    HMR. This registers no second12-qubit allocation and introduces no gates.
    """
    from .jfraction_decoder import GF
    b = builder
    zero = b.alloc_qubits(1)[0]
    b.flip_if_equal(pivot, 0, target=zero)
    b.cx(zero, pivot[0])
    inverse, scaffold = b.init_gf2_inverse_with_scaffold(pivot, field=GF)
    temporary = b.alloc_qubits(12)
    factor, undo_factor = (inverse, pivot) if divide else (pivot, inverse)
    for word in words[:-1]:
        b.ixor_gf2_mul(word, factor, target=temporary, field=GF)
        b.swap(word, temporary)
        b.del_gf2_mul(word, undo_factor, target=temporary, field=GF)
    word = words[-1]
    b.ixor_gf2_mul(word, factor, target=temporary, field=GF)
    b.x(shortened)
    b.cswap(shortened, word, temporary)
    mask = b.alloc_bits(12)
    b.hmr(temporary, mask)
    b.gf2_phase_by_product(word, factor, mask=mask, field=GF)
    b.init_and(shortened, word, temporary)
    b.cx(undo_factor, factor)
    b.gf2_phase_by_product(temporary, factor, mask=mask, field=GF)
    b.cx(undo_factor, factor)
    b.del_and(shortened, word, temporary)
    b.free(mask)
    b.x(shortened)
    b.free(temporary)
    b.del_gf2_inverse_with_scaffold(pivot, target=inverse,
                                   scaffold=scaffold, field=GF)
    b.free(inverse + scaffold)
    b.cx(zero, pivot[0])
    b.flip_if_equal(pivot, 0, target=zero)
    b.free(zero)


def forney_reused_sigma(builder, numerator, denominator_tail, outcomes, *, field):
    """Forney phase with one12-bit word shared by sigma(x) and inverse(D(x)).

    numerator has coefficients Omega[0..34]; denominator_tail has sigma[1..35]
    with implicit sigma[0]=1. Forney evaluates x=alpha^-j. Inputs and scratch
    are restored. Existing tower inverse, retained zero chain and phase-only
    multiplication are reused; the change is the accumulator's lifetime.
    """
    from . import common
    from .compact_euclid import _EnabledZeroTest

    km = common.km
    b = builder
    assert len(numerator) == len(denominator_tail) == 35
    degree = field.degree
    assert degree == 12
    work = b.alloc_qubits(degree)
    flag = b.alloc_qubits(1)[0]
    enabled = b.alloc_bits(1)
    zero_test = _EnabledZeroTest(b, work, True)
    alpha = field.primitive_element
    omega = numerator[0]
    derivative = denominator_tail[0]

    def accumulate_omega():
        for word in numerator[1:]:
            b.cx(word, omega)

    def accumulate_derivative():
        for i in range(2, 35, 2):
            b.cx(denominator_tail[i], derivative)

    def accumulate_sigma():
        b.x(work[0])
        for i in range(1, 35, 2):
            b.cx(denominator_tail[i], work)
        b.cx(derivative, work)

    positions = min((1 << degree) - 1, len(outcomes))
    for j in range(positions):
        b.bit_store(enabled[0], True, control=outcomes[j])
        b.push_condition(enabled[0])
        accumulate_omega()
        accumulate_derivative()
        accumulate_sigma()
        zero_test.flip_if_equal(work, 0, target=flag)
        # Retain the predicate and its exact AND chain, but free the value
        # accumulator using the unchanged coefficient sources.
        accumulate_sigma()
        _, scaffold = b.init_controlled_inverse(derivative, flag, target=work)
        x = field.pow(alpha, -j % ((1 << degree) - 1))
        b.gf2_imul(x, target=omega, field=field)
        b.gf2_phase_by_product(omega, work, mask=outcomes[j], field=field)
        b.gf2_idiv(x, target=omega, field=field)
        b.del_controlled_inverse(derivative, flag, target=work, scaffold=scaffold)
        b.free(scaffold)
        # Inverse deletion has returned work to zero. Recreate sigma(x) so
        # the retained predicate chain can be erased by the upstream MBU.
        accumulate_sigma()
        zero_test.flip_if_equal(work, 0, target=flag)
        accumulate_sigma()
        accumulate_derivative()
        accumulate_omega()
        b.pop_condition()
        b.bit_store(enabled[0], False)
        if j + 1 < positions:
            for i, word in enumerate(denominator_tail, 1):
                b.gf2_imul(field.pow(alpha, -i % 4095), target=word, field=field)
            for i, word in enumerate(numerator):
                if i:
                    b.gf2_imul(field.pow(alpha, -i % 4095), target=word, field=field)
    if positions > 1:
        for i, word in enumerate(denominator_tail, 1):
            b.gf2_imul(field.pow(alpha, i * (positions - 1) % 4095), target=word, field=field)
        for i, word in enumerate(numerator):
            if i:
                b.gf2_imul(field.pow(alpha, i * (positions - 1) % 4095), target=word, field=field)
    assert zero_test.chain is None and zero_test.calls == 2 * positions
    b.free(work + km.array([flag]) + enabled)
