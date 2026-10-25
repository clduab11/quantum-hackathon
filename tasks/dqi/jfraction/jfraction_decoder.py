# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""A 70-word in-place J-fraction DQI phase decoder.

The ordinary J chart is extended reversibly at a zero pivot by using 1 for
its scalar divisions. Exact zero tails are harmless; nonzero tails with a
zero pivot are an explicit decoding approximation. No input is discarded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from .common import build, km
from .static_divisions import StaticArithmeticBuilder, StaticDivisionDecoder
from .compact_euclid import CompactEuclidDecoder
from .model_fast_extraction import power_plan, shear_pieces, toeplitz_plan
from .poly_arithmetic import GF, accumulate_product, add_scaled


def scale_words(builder, pivot, words, *, divide):
    """Multiply or divide all words by pivot, with reversible zero -> 1 extension."""
    if not words:
        return
    zero = builder.alloc_qubits(1)[0]
    builder.flip_if_equal(pivot, 0, target=zero)
    builder.cx(zero, pivot[0])
    inverse, scaffold = builder.init_gf2_inverse_with_scaffold(pivot, field=GF)
    temporary = builder.alloc_qubits(12)
    factor, undo_factor = (inverse, pivot) if divide else (pivot, inverse)
    for word in words:
        builder.ixor_gf2_mul(word, factor, target=temporary, field=GF)
        builder.swap(word, temporary)
        builder.del_gf2_mul(word, undo_factor, target=temporary, field=GF)
    builder.free(temporary)
    builder.del_gf2_inverse_with_scaffold(pivot, target=inverse,
                                          scaffold=scaffold, field=GF)
    builder.free(inverse + scaffold)
    builder.cx(zero, pivot[0])
    builder.flip_if_equal(pivot, 0, target=zero)
    builder.free(zero)


def shear(builder, source, target, d, m, *, constant_zero=False):
    """Add the product's cross block; all source cells survive unchanged."""
    n = len(target)
    for piece in shear_pieces(n, d, constant_zero, m):
        ii, jj = piece['is'], piece['js']
        assert ii == list(range(ii[0], ii[-1] + 1))
        assert jj == list(range(jj[0], jj[-1] + 1, d))
        lhs = [source[i] for i in ii]
        rhs = [target[j] for j in jj]
        outputs = []
        for k in range(len(ii) + len(jj) - 1):
            physical = d * (ii[0] + k) + jj[0]
            outputs.append(target[physical] if m <= physical < n else None)
        accumulate_product(builder, lhs, rhs, outputs, left_frobenius=d)
    if constant_zero:
        for i in range(1, (n - 1) // d + 1):
            if m <= d * i < n:
                add_scaled(builder, source[i], target[d * i], frobenius=d)


def toeplitz(builder, source, target, d, *, reverse=False):
    n = len(target)
    if n <= d:
        return
    _, m = toeplitz_plan(n, d)
    if reverse:
        toeplitz(builder, source, target[:m], d, reverse=True)
        shear(builder, source, target, d, m)
        toeplitz(builder, source, target[m:], d, reverse=True)
    else:
        toeplitz(builder, source, target[m:], d)
        shear(builder, source, target, d, m)
        toeplitz(builder, source, target[:m], d)


def power_map(builder, words, d, *, reverse=False):
    n = len(words)
    if n <= d:
        return
    _, m = power_plan(n, d)
    if reverse:
        power_map(builder, words[:m], d, reverse=True)
        shear(builder, words, words, d, m, constant_zero=True)
        toeplitz(builder, words, words[m:], d, reverse=True)
    else:
        toeplitz(builder, words, words[m:], d)
        shear(builder, words, words, d, m, constant_zero=True)
        power_map(builder, words[:m], d)


def reciprocal(builder, words, *, reverse=False):
    assert words[0] == 1
    d, exponent, factors = 2, 1, []
    while exponent < len(words) - 1:
        factors.append(d)
        exponent *= 1 + d
        d *= d
    for factor in reversed(factors) if reverse else factors:
        power_map(builder, words, factor, reverse=reverse)


def extract(builder, words, *, reverse=False):
    assert len(words) % 2 == 0
    levels = range(0, len(words), 2)
    for start in reversed(levels) if reverse else levels:
        active = words[start:]
        if reverse:
            reciprocal(builder, [1] + active[1:], reverse=True)
            scale_words(builder, active[0], active[1:], divide=False)
        else:
            scale_words(builder, active[0], active[1:], divide=True)
            reciprocal(builder, [1] + active[1:])


def conversion_layout(words):
    p, q, stages = [], [1], []
    for start in reversed(range(0, len(words), 2)):
        c, a = words[start:start + 2]
        stages.append((c, a, list(p), list(q)))
        p, q = [c] + q[1:], [1, a] + p
    return p, q, stages


def convert(builder, words, *, reverse=False):
    p, q, stages = conversion_layout(words)
    for c, a, old_p, old_q in reversed(stages) if reverse else stages:
        k = len(old_p)
        if reverse:
            scale_words(builder, c, old_q[1:], divide=True)
            if k:
                builder.cx(old_q[1], a)
        for j in range(2, k + 2):
            if j <= k:
                builder.cx(old_q[j], old_p[j - 2])
            builder.ixor_gf2_mul(a, old_q[j - 1], target=old_p[j - 2], field=GF)
        if not reverse:
            if k:
                builder.cx(old_q[1], a)
            scale_words(builder, c, old_q[1:], divide=False)
    return p, q


class JFractionDecoder(StaticDivisionDecoder):
    def build_syndrome_decoding_mbuc(self, builder, *, syndromes, error_mbuc, n_iters):
        assert len(syndromes) == 70 and len(error_mbuc) == 4095
        b, words = builder, list(syndromes)
        b.stage_records = []
        self._record(b, "initialization")
        extract(b, words)
        self._record(b, "moment_to_fraction")
        numerator, denominator = convert(b, words)
        self._record(b, "fraction_to_polynomials")
        one = b.alloc_qubits(12)
        b.x(one[0])
        denominator[0] = one
        CompactEuclidDecoder(70, self.field)._forney(
            b, numerator, denominator, True, error_mbuc)
        b.x(one[0])
        b.free(one)
        self._record(b, "phase_correction")
        convert(b, words, reverse=True)
        self._record(b, "polynomials_to_fraction")
        extract(b, words, reverse=True)
        self._record(b, "fraction_to_moments")




