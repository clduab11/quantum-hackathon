# SPDX-License-Identifier: Apache-2.0
"""GF(2) linear algebra on Python integers: one integer is one bit vector.

A basis is a dict that maps the leading bit of a row to the row. Every routine is exact and deterministic.
"""


def reduce(basis, vector):
    """Reduce `vector` by `basis`. The result is zero exactly when `vector` is in the span."""
    while vector:
        lead = vector.bit_length() - 1
        row = basis.get(lead)
        if row is None:
            return vector
        vector ^= row
    return 0


def insert(basis, vector):
    """Add `vector` to `basis`. Returns True when it was independent of the rows already there."""
    vector = reduce(basis, vector)
    if vector:
        basis[vector.bit_length() - 1] = vector
        return True
    return False


def span_basis(vectors, basis=None):
    """A basis of the span of `vectors`, optionally extending a copy of `basis`."""
    basis = dict(basis or {})
    for vector in vectors:
        insert(basis, vector)
    return basis


def reduced(basis):
    """Reduced row echelon form of `basis` as a dict: no row has a bit at another row's leading bit."""
    basis = dict(basis)
    leads = sorted(basis)
    for lead in leads:
        row = basis[lead]
        for other in leads:
            if other > lead and (basis[other] >> lead) & 1:
                basis[other] ^= row
    return basis


def canonical(vectors):
    """A tuple that is equal for two sets of vectors exactly when they span the same subspace."""
    basis = reduced(span_basis(vectors))
    return tuple(basis[lead] for lead in sorted(basis))


def nullspace(rows, columns):
    """Basis of {f in GF(2)^columns : parity(row & f) = 0 for every row}."""
    basis = reduced(span_basis(rows))
    leads = sorted(basis)
    pivots = set(leads)
    out = []
    for free in range(columns):
        if free in pivots:
            continue
        vector = 1 << free
        for lead in leads:
            if (basis[lead] >> free) & 1:
                vector |= 1 << lead
        out.append(vector)
    return out


class Combinations:
    """Echelon form of generators that remembers how each row was built from them.

    `solve(target)` returns a bit mask over the generator indices whose XOR equals `target`,
    or None when `target` is outside the span. Dependent generators get no pivot, so their bit
    is never set in a solution.
    """

    def __init__(self, generators):
        self.rows = {}
        for index, vector in enumerate(generators):
            combo = 1 << index
            while vector:
                lead = vector.bit_length() - 1
                known = self.rows.get(lead)
                if known is None:
                    self.rows[lead] = (vector, combo)
                    break
                vector ^= known[0]
                combo ^= known[1]

    def solve(self, target):
        combo = 0
        while target:
            known = self.rows.get(target.bit_length() - 1)
            if known is None:
                return None
            target ^= known[0]
            combo ^= known[1]
        return combo
