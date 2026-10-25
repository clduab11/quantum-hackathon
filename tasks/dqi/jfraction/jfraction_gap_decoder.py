# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Two-slot 3+1 J-fraction gap repair with a shared inversion kernel.

One flag per slot records a first-order zero pivot. Its successor uses a
one-coefficient Stieltjes extraction. Both reuse the ordinary block maps;
only a top coefficient, rotations, and linear conversion terms are controlled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from .jfraction_decoder import (GF, JFractionDecoder, StaticArithmeticBuilder,
                               add_scaled, build, conversion_layout, km,
                               power_map, scale_words)
from .compact_euclid import CompactEuclidDecoder


def rotate(builder, words, control, *, left):
    if control is False or len(words) < 2:
        return
    order = range(len(words) - 1)
    for i in order if left else reversed(order):
        if control is True:
            builder.swap(words[i], words[i + 1])
        else:
            builder.cswap(control, words[i], words[i + 1])


def toggle_gap(builder, words, previous, gap):
    if previous is not False:
        builder.x(previous)
    control = True if previous is False else previous
    builder.flip_if_equal(words[0], 0, target=gap, control=control)
    builder.flip_if_equal(words[0] + words[1], 0, target=gap, control=control)
    if previous is not False:
        builder.x(previous)


def scale_active(builder, pivot, words, shortened, *, divide):
    """Scale all but the last word unconditionally; preserve the last if shortened."""
    zero = builder.alloc_qubits(1)[0]
    builder.flip_if_equal(pivot, 0, target=zero)
    builder.cx(zero, pivot[0])
    inverse, scaffold = builder.init_gf2_inverse_with_scaffold(pivot, field=GF)
    temporary = builder.alloc_qubits(12)
    factor, undo_factor = (inverse, pivot) if divide else (pivot, inverse)
    for word in words[:-1]:
        builder.ixor_gf2_mul(word, factor, target=temporary, field=GF)
        builder.swap(word, temporary)
        builder.del_gf2_mul(word, undo_factor, target=temporary, field=GF)
    # If active, temporary is the old word; otherwise it is word*factor.
    # Its phase is word*factor + active*word*(factor+undo_factor).
    word = words[-1]
    builder.ixor_gf2_mul(word, factor, target=temporary, field=GF)
    builder.x(shortened)
    builder.cswap(shortened, word, temporary)
    mask = builder.alloc_bits(12)
    builder.hmr(temporary, mask)
    builder.gf2_phase_by_product(word, factor, mask=mask, field=GF)
    masked = builder.alloc_qubits(12)
    builder.init_and(shortened, word, masked)
    builder.cx(undo_factor, factor)
    builder.gf2_phase_by_product(masked, factor, mask=mask, field=GF)
    builder.cx(undo_factor, factor)
    builder.del_and(shortened, word, masked)
    builder.free(masked + mask)
    builder.x(shortened)
    builder.free(temporary)
    builder.del_gf2_inverse_with_scaffold(pivot, target=inverse,
                                          scaffold=scaffold, field=GF)
    builder.free(inverse + scaffold)
    builder.cx(zero, pivot[0])
    builder.flip_if_equal(pivot, 0, target=zero)
    builder.free(zero)


def top_power_update(builder, words, d, shortened):
    """Update the highest coefficient only on the ordinary (full-length) path."""
    last = len(words) - 1
    terms = [(i, last - d * i) for i in range(1, last // d + 1)]
    if not terms:
        return
    assert all(j > 0 for _, j in terms)  # Every active length is even.
    delta, frobenius = builder.alloc_qubits(12), builder.alloc_qubits(12)
    for i, j in terms:
        add_scaled(builder, words[i], frobenius, frobenius=d)
        builder.ixor_gf2_mul(frobenius, words[j], target=delta, field=GF)
        add_scaled(builder, words[i], frobenius, frobenius=d)
    builder.x(shortened)
    builder.gf2_iadd(delta, target=words[-1], control=shortened, field=GF)
    builder.x(shortened)
    mask = builder.alloc_bits(12)
    builder.hmr(delta, mask)
    for i, j in terms:
        add_scaled(builder, words[i], frobenius, frobenius=d)
        builder.gf2_phase_by_product(frobenius, words[j], mask=mask, field=GF)
        add_scaled(builder, words[i], frobenius, frobenius=d)
    builder.free(mask + delta + frobenius)


def reciprocal_active(builder, words, shortened, *, reverse=False):
    assert words[0] == 1 and len(words) % 2 == 0
    d, exponent, factors = 2, 1, []
    while exponent < len(words) - 1:
        factors.append(d)
        exponent *= 1 + d
        d *= d
    for factor in reversed(factors) if reverse else factors:
        if reverse:
            power_map(builder, words[:-1], factor, reverse=True)
            top_power_update(builder, words, factor, shortened)
        else:
            top_power_update(builder, words, factor, shortened)
            power_map(builder, words[:-1], factor)


def extract_gap(builder, words, flags, *, reverse=False):
    slots = len(words) // 2
    assert len(flags) == slots
    for j in reversed(range(slots)) if reverse else range(slots):
        active = words[2 * j:]
        previous = flags[j - 1] if j else False
        gap = flags[j]
        if not reverse:
            toggle_gap(builder, active, previous, gap)
        shortened = builder.alloc_qubits(1)[0]
        builder.cx(gap, shortened)
        if j:
            builder.cx(previous, shortened)
        rotate(builder, active, shortened, left=True)
        if reverse:
            reciprocal_active(builder, [1] + active[1:], shortened, reverse=True)
            scale_active(builder, active[0], active[1:], shortened, divide=False)
        else:
            scale_active(builder, active[0], active[1:], shortened, divide=True)
            reciprocal_active(builder, [1] + active[1:], shortened)
        rotate(builder, active, shortened, left=False)
        if j:
            builder.cx(previous, shortened)
        builder.cx(gap, shortened)
        builder.free(shortened)
        if reverse:
            toggle_gap(builder, active, previous, gap)


def conversion_core(builder, y, old_p, old_q, pending):
    k = len(old_p)
    if not k:
        return
    if pending is False:
        mu = y
    else:
        mu = builder.alloc_qubits(12)
        builder.x(pending)
        builder.init_and(pending, y, mu)
        builder.x(pending)
        builder.cx(pending, mu[0])
    for i in range(k):
        builder.ixor_gf2_mul(mu, old_q[i + 1], target=old_p[i], field=GF)
    if pending is not False:
        builder.cx(pending, mu[0])
        builder.x(pending)
        builder.del_and(pending, y, mu)
        builder.x(pending)
        builder.free(mu)
        builder.x(pending)
    control = True if pending is False else pending
    for i in range(k - 1):
        builder.gf2_iadd(old_q[i + 2], target=old_p[i], control=control, field=GF)
    if pending is not False:
        builder.x(pending)


def toggle_header(builder, y, old_q, pending):
    if len(old_q) == 1:
        return
    if pending is not False:
        builder.x(pending)
    builder.gf2_iadd(old_q[1], target=y,
                     control=True if pending is False else pending, field=GF)
    if pending is not False:
        builder.x(pending)


def convert_gap(builder, words, flags, *, reverse=False):
    p, q, stages = conversion_layout(words)
    stages = [(len(flags) - 1 - i, *stage) for i, stage in enumerate(stages)]
    for j, x, y, old_p, old_q in reversed(stages) if reverse else stages:
        pending = flags[j - 1] if j else False
        gap = flags[j]
        new_p = [x] + old_q[1:]
        rotations = [x, y] + old_q[1:]
        if reverse:
            rotate(builder, new_p, gap, left=True)
            scale_words(builder, x, old_q[1:], divide=True)
            toggle_header(builder, y, old_q, pending)
        else:
            if j:
                builder.cswap(pending, x, y)
            rotate(builder, rotations, gap, left=True)
        conversion_core(builder, y, old_p, old_q, pending)
        if reverse:
            rotate(builder, rotations, gap, left=False)
            if j:
                builder.cswap(pending, x, y)
        else:
            toggle_header(builder, y, old_q, pending)
            scale_words(builder, x, old_q[1:], divide=False)
            rotate(builder, new_p, gap, left=False)
    return p, q


class GapJFractionDecoder(JFractionDecoder):
    def build_syndrome_decoding_mbuc(self, builder, *, syndromes, error_mbuc, n_iters):
        b, words = builder, list(syndromes)
        b.stage_records = []
        flags = b.alloc_qubits(35)
        self._record(b, "initialization")
        extract_gap(b, words, flags)
        self._record(b, "moment_to_fraction")
        numerator, denominator = convert_gap(b, words, flags)
        self._record(b, "fraction_to_polynomials")
        one = b.alloc_qubits(12)
        b.x(one[0])
        denominator[0] = one
        CompactEuclidDecoder(70, self.field)._forney(
            b, numerator, denominator, True, error_mbuc)
        b.x(one[0])
        b.free(one)
        self._record(b, "phase_correction")
        convert_gap(b, words, flags, reverse=True)
        self._record(b, "polynomials_to_fraction")
        extract_gap(b, words, flags, reverse=True)
        b.free(flags)
        self._record(b, "fraction_to_moments")




