# SPDX-License-Identifier: Apache-2.0
# Port of SomeJoint v7; see PROVENANCE.md and SOURCE_MAP.json.
# Praxen: package imports; production functions only; no notebook runtime.
"Zero-clean-word polynomial accumulation via in-place linear forms.\n\nEvaluation/middle-product decompositions and output conjugation follow the\nread SomeJoint/Agniv Banerjee Apache-2.0 `poly_arithmetic.py`. This independent\nvariant exposes each operand linear form inside one of that operand's words,\nthen restores it. Operand banks must be disjoint (unlike the general source)."
from __future__ import annotations

from contextlib import contextmanager
from functools import cache
from ..jfraction.poly_arithmetic import GF, add_scaled, interpolation_columns, product_vector
from ..jfraction.tower import elimination_gates


@cache
def word_map(coefficient, frobenius):
    columns = [GF.mul(coefficient, GF.pow(1 << i, frobenius)) for i in range(12)]
    return tuple(elimination_gates(columns))


def transform_word(b, word, coefficient=1, frobenius=1, *, inverse=False):
    gates = word_map(coefficient, frobenius)
    for gate, a, c in gates if inverse else reversed(gates):
        getattr(b, gate)(word[a], word[c])


@contextmanager
def linear_form(b, words, coefficients, frobenius=1):
    """Yield a field word or classical integer, with every source restored."""
    constant = 0
    by_word = {}
    for word, coefficient in zip(words, coefficients):
        if not coefficient:
            continue
        if isinstance(word, int):
            constant ^= GF.mul(coefficient, GF.pow(word, frobenius))
        else:
            key = tuple(word)
            if key in by_word:
                by_word[key][1] ^= coefficient
            else:
                by_word[key] = [word, coefficient]
    live = [(w, c) for w, c in by_word.values() if c]
    if not live:
        yield constant
        return
    pivot, coefficient = live[0]
    others = live[1:]
    transform_word(b, pivot, coefficient, frobenius)
    for word, value in others:
        add_scaled(b, word, pivot, value, frobenius)
    if constant:
        b.gf2_iadd(constant, target=pivot, field=GF)
    try:
        yield pivot
    finally:
        if constant:
            b.gf2_iadd(constant, target=pivot, field=GF)
        for word, value in reversed(others):
            add_scaled(b, word, pivot, value, frobenius)
        transform_word(b, pivot, coefficient, frobenius, inverse=True)


def vector_product(b, lhs, rhs, outputs, coefficients):
    if isinstance(lhs, int) or isinstance(rhs, int):
        if isinstance(rhs, int):
            lhs, rhs = rhs, lhs
        for target, coefficient in zip(outputs, coefficients):
            if target is not None and coefficient:
                add_scaled(b, rhs, target, GF.mul(lhs, coefficient))
        return 0
    return product_vector(b, lhs, rhs, outputs, coefficients)


def accumulate(b, lhs, rhs, outputs, *, left_frobenius=1,
               right_frobenius=1, method="auto"):
    size = len(lhs)+len(rhs)-1
    assert len(outputs) == size
    left_ids = {q for w in lhs if not isinstance(w, int) for q in w}
    right_ids = {q for w in rhs if not isinstance(w, int) for q in w}
    target_ids = [q for w in outputs if w is not None for q in w]
    assert not left_ids.intersection(right_ids), "operand banks must be disjoint"
    assert not (left_ids | right_ids).intersection(target_ids)
    assert len(target_ids) == len(set(target_ids))
    active = [i for i, word in enumerate(outputs) if word is not None]
    if not active:
        return 0
    first, last = active[0], active[-1]
    span = last-first+1
    terms = [(i, j) for i in range(len(lhs)) for j in range(len(rhs))
             if outputs[i+j] is not None]
    middle_rank = min(len(lhs), len(rhs))+span-1
    if method == "auto":
        method = min((len(terms), "schoolbook"), (size, "evaluation"),
                     (middle_rank, "middle"))[1]
    assert method in ("schoolbook", "evaluation", "middle")
    count = 0
    if method == "schoolbook":
        for i, j in terms:
            with linear_form(b, [lhs[i]], [1], left_frobenius) as a:
                with linear_form(b, [rhs[j]], [1], right_frobenius) as c:
                    count += vector_product(b, a, c, [outputs[i+j]], [1])
    elif method == "evaluation":
        for point, weights in enumerate(interpolation_columns(size)):
            if not any(w is not None and c for w, c in zip(outputs, weights)):
                continue
            with linear_form(b, lhs, [GF.pow(point, i) for i in range(len(lhs))], left_frobenius) as a:
                with linear_form(b, rhs, [GF.pow(point, i) for i in range(len(rhs))], right_frobenius) as c:
                    count += vector_product(b, a, c, outputs, weights)
    else:
        if len(lhs) < len(rhs):
            lhs, rhs = rhs, lhs
            left_frobenius, right_frobenius = right_frobenius, left_frobenius
        rr = list(reversed(rhs))
        out = outputs[first:last+1]
        for point, lagrange in enumerate(interpolation_columns(middle_rank)):
            coefficients = [0]*len(lhs)
            for i, value in enumerate(lagrange):
                index = first-len(rhs)+1+i
                if 0 <= index < len(lhs):
                    coefficients[index] ^= value
            weights = [GF.pow(point, i) for i in range(span)]
            if not any(coefficients) or not any(w is not None and c for w, c in zip(out, weights)):
                continue
            with linear_form(b, lhs, coefficients, left_frobenius) as a:
                with linear_form(b, rr, [GF.pow(point, i) for i in range(len(rr))], right_frobenius) as c:
                    count += vector_product(b, a, c, out, weights)
    return count


def triangular(b, coefficients, words, *, divide=False, frobenius=1):
    """Unit-diagonal truncated series product/solve; no clean scratch words."""
    assert coefficients[0] == 1
    n = len(words)
    if n <= 1:
        return 0
    m = n//2

    def low():
        return triangular(b, coefficients, words[:m], divide=divide, frobenius=frobenius)

    def high():
        return triangular(b, coefficients, words[m:], divide=divide, frobenius=frobenius)

    def shear():
        lhs = [0]+list(coefficients[1:n])
        lhs += [0]*(n-len(lhs))
        out = [None]*(n+m-1)
        out[m:n] = words[m:]
        return accumulate(b, lhs, words[:m], out, left_frobenius=frobenius)

    return sum(action() for action in ((low, shear, high) if divide else (high, shear, low)))


def barnett(b, polynomial_without_monic_lead, words, *, reverse=False):
    """Apply Bez(P,1), for monic P, to an n-word coefficient vector."""
    n = len(words)
    coefficients = [1]+list(reversed(polynomial_without_monic_lead))

    def reversal():
        for i in range(n//2):
            b.swap(words[i], words[n-1-i])

    if reverse:
        reversal()
    count = triangular(b, coefficients, words, divide=reverse)
    if not reverse:
        reversal()
    return count
