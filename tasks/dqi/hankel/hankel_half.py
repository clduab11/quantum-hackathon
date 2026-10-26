# SPDX-License-Identifier: Apache-2.0
# Port of SomeJoint v7; see PROVENANCE.md and SOURCE_MAP.json.
# Praxen: package imports; production functions only; no notebook runtime.
"T8: fuse half-degree Forney reconstruction into one monic Hankel map.\n\nThe starting R42/R43 half-degree identity and this run's Bezoutian solver\nare credited in central2/half_circuit.py. This factorization uses\nquot(A * Bez(B,1) z / B) = Bez(A,1) z. A single degree-(2n+1)\nBarnett map replaces the two degree-n maps and quotient reconstruction.\nThe first even coefficient needs the explicit dot(B_low,z1) correction."
from __future__ import annotations

from collections import Counter
from . import inplace_poly as poly
from .border_circuit import apply_border, GF
from .central_circuit import central_border
from .forney_bezout import root_scan


def output_words(numerator):
    reverse = list(reversed(numerator))
    c, d = reverse[::2], reverse[1::2]
    return [word for pair in zip(d, c[:-1]) for word in pair]+[c[-1]]


def transform(b, numerator, denominator_tail, *, reverse=False,
              border=apply_border, counts=None):
    size = len(numerator)
    assert size % 2 == 1 and len(denominator_tail) == size
    n = size//2
    assert n >= 1
    counts = Counter() if counts is None else counts
    locator = list(reversed(denominator_tail))
    a, bb = locator[::2], locator[1::2]
    omega = list(reversed(numerator))
    c, dd = omega[::2], omega[1::2]
    h0, h1, scalar = c[:-1], dd, c[-1]
    result = output_words(numerator)

    def basis(inverse):
        for word in [*locator, *omega]:
            poly.transform_word(b, word, frobenius=2 if inverse else 2048)

    def reduce_a():
        for i in range(n):
            b.ixor_gf2_mul(a[-1], bb[i], target=a[i], field=GF)
            counts['outer_products'] += 1

    def reduce_c():
        for i in range(n):
            b.ixor_gf2_mul(scalar, bb[i], target=h0[i], field=GF)
            counts['outer_products'] += 1

    def correction():
        for coefficient, value in zip(bb, h1):
            b.ixor_gf2_mul(coefficient, value, target=scalar, field=GF)
            counts['outer_products'] += 1

    basis(False)
    if not reverse:
        reduce_a()
        reduce_c()
        border(b, bb, a[:-1], [h0, h1], counts, monic=True)
        reduce_a()
        correction()
        counts['outer_products'] += poly.barnett(b, locator, result)
    else:
        counts['outer_products'] += poly.barnett(b, locator, result, reverse=True)
        correction()
        reduce_a()
        border(b, bb, a[:-1], [h0, h1], counts, reverse=True, monic=True)
        reduce_c()
        reduce_a()
    basis(True)
    return result


def forney(b, numerator, denominator_tail, outcomes, *, field):
    counts = Counter()
    values = transform(b, numerator, denominator_tail, counts=counts, border=central_border)
    root_scan(b, values, denominator_tail, outcomes, field=field)
    transform(b, numerator, denominator_tail, reverse=True, counts=counts, border=central_border)
    b.bezout_phase_arithmetic = dict(counts)
