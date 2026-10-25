# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Low-workspace polynomial product accumulation over the benchmark field.

Evaluation/interpolation is a bilinear decomposition. Two field words hold
operand linear forms; conjugating the output words sends one product to an
arbitrary coefficient vector. The output may be dirty, but must be disjoint
from the operand words. All constant linear maps are Clifford operations.
"""
from __future__ import annotations

from functools import cache
from pathlib import Path
import sys

from .common import km

GF = km.GF2Field(12)


@cache
def linear_columns(coefficient: int, frobenius: int = 1):
    return tuple(GF.mul(coefficient, GF.pow(1 << bit, frobenius))
                 for bit in range(12))


def add_scaled(builder, source, target, coefficient=1, frobenius=1):
    """target ^= coefficient * source**frobenius, for Frobenius powers of 2."""
    if not coefficient:
        return
    assert frobenius > 0 and frobenius & (frobenius - 1) == 0
    if isinstance(source, int):
        value = GF.mul(coefficient, GF.pow(source, frobenius))
        if value:
            builder.gf2_iadd(value, target=target, field=GF)
        return
    lhs, rhs = [], []
    for bit, column in enumerate(linear_columns(coefficient, frobenius)):
        for out in range(12):
            if column >> out & 1:
                lhs.append(source[bit])
                rhs.append(target[out])
    if lhs:
        builder.cx(km.array(lhs), km.array(rhs))


@cache
def interpolation_columns(size: int):
    """Lagrange polynomials for the distinct field elements 0..size-1."""
    assert 1 <= size <= 4096
    polynomial = [1]
    for point in range(size):
        out = [0] * (len(polynomial) + 1)
        for i, value in enumerate(polynomial):
            out[i] ^= GF.mul(point, value)
            out[i + 1] ^= value
        polynomial = out
    result = []
    for point in range(size):
        quotient = [0] * size
        quotient[-1] = polynomial[-1]
        for i in range(size - 1, 0, -1):
            quotient[i - 1] = polynomial[i] ^ GF.mul(point, quotient[i])
        assert polynomial[0] == GF.mul(point, quotient[0])
        denominator = 1
        for other in range(size):
            if other != point:
                denominator = GF.mul(denominator, point ^ other)
        inverse = GF.div(1, denominator)
        result.append(tuple(GF.mul(value, inverse) for value in quotient))
    return tuple(result)


def add_evaluation(builder, words, point, target, frobenius=1):
    coefficient = 1
    for word in words:
        add_scaled(builder, word, target, coefficient, frobenius)
        coefficient = GF.mul(coefficient, point)


def product_vector(builder, lhs, rhs, targets, coefficients):
    """targets[i] ^= coefficients[i] * lhs * rhs using one field product."""
    live = [(word, value) for word, value in zip(targets, coefficients)
            if word is not None and value]
    if not live:
        return 0
    pivot, scale = live[0]
    others = [(word, GF.div(value, scale)) for word, value in live[1:]]
    for word, value in others:
        add_scaled(builder, pivot, word, value)
    if scale != 1:
        builder.gf2_idiv(scale, target=pivot, field=GF)
    builder.ixor_gf2_mul(lhs, rhs, target=pivot, field=GF)
    if scale != 1:
        builder.gf2_imul(scale, target=pivot, field=GF)
    for word, value in reversed(others):
        add_scaled(builder, pivot, word, value)
    return 1


def accumulate_product(builder, lhs, rhs, targets, *, left_frobenius=1,
                       right_frobenius=1, method="auto"):
    """Accumulate selected coefficients of a polynomial product.

    `targets` has len(lhs)+len(rhs)-1 entries; None suppresses a coefficient.
    Frobenius acts on coefficients, not on polynomial exponents. Source
    operands may alias one another. Targets must be pairwise disjoint and
    disjoint from all sources. Returns the actual number of field products.
    """
    size = len(lhs) + len(rhs) - 1
    assert len(lhs) and len(rhs) and len(targets) == size
    input_ids = {q for word in [*lhs, *rhs] if not isinstance(word, int)
                 for q in word}
    target_ids = [q for word in targets if word is not None for q in word]
    assert len(target_ids) == len(set(target_ids))
    assert not input_ids.intersection(target_ids)
    terms = [(i, j, targets[i + j]) for i in range(len(lhs))
             for j in range(len(rhs)) if targets[i + j] is not None]
    if not terms:
        return 0
    first = next(i for i, word in enumerate(targets) if word is not None)
    last = max(i for i, word in enumerate(targets) if word is not None)
    span = last - first + 1
    middle_rank = min(len(lhs), len(rhs)) + span - 1
    assert method in ("auto", "schoolbook", "evaluation", "middle")
    if method == "auto":
        method = min((len(terms), "schoolbook"), (size, "evaluation"),
                     (middle_rank, "middle"))[1]
    a, b = builder.alloc_qubits(12), builder.alloc_qubits(12)
    products = 0
    if method == "schoolbook":
        for i, j, target in terms:
            add_scaled(builder, lhs[i], a, frobenius=left_frobenius)
            add_scaled(builder, rhs[j], b, frobenius=right_frobenius)
            builder.ixor_gf2_mul(a, b, target=target, field=GF)
            add_scaled(builder, rhs[j], b, frobenius=right_frobenius)
            add_scaled(builder, lhs[i], a, frobenius=left_frobenius)
            products += 1
    elif method == "evaluation":
        for point, coefficients in enumerate(interpolation_columns(size)):
            if not any(word is not None and coefficient
                       for word, coefficient in zip(targets, coefficients)):
                continue
            add_evaluation(builder, lhs, point, a, left_frobenius)
            add_evaluation(builder, rhs, point, b, right_frobenius)
            products += product_vector(builder, a, b, targets, coefficients)
            add_evaluation(builder, rhs, point, b, right_frobenius)
            add_evaluation(builder, lhs, point, a, left_frobenius)
    else:
        # Transpose multiplication of reverse(rhs) by an output covector.
        # For output k=first+t, its coefficient pairing is
        # sum_l lhs[first-len(rhs)+1+l] * (reverse(rhs)*covector)[l].
        # Interpolation gives a linear form of lhs, evaluation gives a
        # linear form of reverse(rhs), and output weights are point**t.
        if len(lhs) < len(rhs):
            lhs, rhs = rhs, lhs
            left_frobenius, right_frobenius = right_frobenius, left_frobenius
        reversed_rhs = list(reversed(rhs))
        out = targets[first:last + 1]
        for point, lagrange in enumerate(interpolation_columns(middle_rank)):
            linear_terms = [(first - len(rhs) + 1 + i, value)
                            for i, value in enumerate(lagrange)
                            if value and 0 <= first - len(rhs) + 1 + i < len(lhs)]
            if not linear_terms:
                continue
            weights = [GF.pow(point, i) for i in range(span)]
            if not any(word is not None and weight for word, weight in zip(out, weights)):
                continue
            for i, value in linear_terms:
                add_scaled(builder, lhs[i], a, value, left_frobenius)
            add_evaluation(builder, reversed_rhs, point, b, right_frobenius)
            products += product_vector(builder, a, b, out, weights)
            add_evaluation(builder, reversed_rhs, point, b, right_frobenius)
            for i, value in reversed(linear_terms):
                add_scaled(builder, lhs[i], a, value, left_frobenius)
    builder.free(a + b)
    return products
