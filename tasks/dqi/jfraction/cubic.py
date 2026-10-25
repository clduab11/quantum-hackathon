# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""45-Toffoli GF(4096) multiplication via five GF(16) evaluations.

Retains v4's EEA and the 75-Toffoli quadratic-tower inverse. Only the full
12-bit multiplier uses a cubic extension and Toom interpolation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from .common import build, km  # noqa: E402
from .tower import elimination_gates, xor_columns  # noqa: E402
from .narrow import NarrowBuilder  # noqa: E402
from .sweep import ReducedSweepDecoder  # noqa: E402


def invert_matrix(rows, field):
    n = len(rows)
    work = [list(row) + [int(i == j) for j in range(n)] for i, row in enumerate(rows)]
    for i in range(n):
        pivot = next(j for j in range(i, n) if work[j][i])
        work[i], work[pivot] = work[pivot], work[i]
        scale = field.invert(work[i][i])
        work[i] = [field.mul(x, scale) for x in work[i]]
        for j in range(n):
            if i != j and work[j][i]:
                scale = work[j][i]
                work[j] = [a ^ field.mul(scale, b) for a, b in zip(work[j], work[i])]
    assert [row[:n] for row in work] == [[int(i == j) for j in range(n)] for i in range(n)]
    return [row[n:] for row in work]


class EvaluationBasis:
    """Polynomial interpolation for an extension of degree d over GF(2**h)."""

    def __init__(self, degree=12, subdegree=4):
        assert degree % subdegree == 0
        h, d = subdegree, degree // subdegree
        assert 2*d - 2 <= 1 << h
        self.subdegree, self.extension_degree = h, d
        outer, inner = km.GF2Field(degree), km.GF2Field(h)
        self.outer, self.inner = outer, inner
        beta = next(x for x in range(2, 1 << degree)
                    if xor_columns([outer.pow(x, k) for k in range(h+1)], inner.modulus) == 0)
        embedded = [outer.pow(beta, i) for i in range(h)]
        theta = outer.primitive_element
        self.columns = [outer.mul(outer.pow(theta, j), e) for j in range(d) for e in embedded]
        self.to_cubic = elimination_gates(self.columns)
        coordinates = {xor_columns(self.columns, i): i for i in range(1 << degree)}
        assert len(coordinates) == 1 << degree
        self.beta, self.theta = beta, theta
        mask = (1 << h) - 1
        self.relation = tuple((coordinates[outer.pow(theta, d)] >> (h*j)) & mask for j in range(d))

        count = 2*d - 1
        self.points = (*range(count - 1), None)
        evaluation = [[inner.pow(t, k) for k in range(count)] if t is not None else [0]*(count-1) + [1]
                      for t in self.points]
        interpolate = invert_matrix(evaluation, inner)
        self.weights = []
        for t in range(count):
            weight = 0
            for k in range(count):
                weight ^= outer.mul(xor_columns(embedded, interpolate[k][t]), outer.pow(theta, k))
            packed = coordinates[weight]
            self.weights.append(tuple((packed >> (h*j)) & mask for j in range(d)))
        self.linear_columns = {c: [inner.mul(c, 1 << j) for j in range(h)] for c in range(1 << h)}

    def change_basis(self, builder, reg, *, to_cubic):
        gates = self.to_cubic if to_cubic else reversed(self.to_cubic)
        for kind, a, b in gates:
            getattr(builder, kind)(reg[a], reg[b])

    def add_scaled(self, builder, source, target, scale):
        pairs = [(i, j) for i, column in enumerate(self.linear_columns[scale])
                 for j in range(self.subdegree) if column >> j & 1]
        if pairs:
            builder.cx(km.array([source[i] for i, _ in pairs]), km.array([target[j] for _, j in pairs]))


class CubicBuilder(NarrowBuilder):
    def __init__(self, decompositions=((12, 4),)):
        super().__init__()
        self.evaluation_bases = {n: EvaluationBasis(n, h) for n, h in decompositions}
        self.cubic = self.evaluation_bases[12]

    def _multiply(self, lhs, rhs, target):
        if len(lhs) not in self.evaluation_bases:
            return super()._multiply(lhs, rhs, target)
        b, basis = self.native, self.evaluation_bases[len(lhs)]
        f = basis.inner
        h, d = basis.subdegree, basis.extension_degree
        with b.mark('cubic_multiply'):
            for reg in (lhs, rhs, target):
                basis.change_basis(b, reg, to_cubic=True)
            aa = [lhs[h*i:h*(i+1)] for i in range(d)]
            bb = [rhs[h*i:h*(i+1)] for i in range(d)]
            cc = [target[h*i:h*(i+1)] for i in range(d)]
            for point, weights in zip(basis.points, basis.weights):
                if point is not None:
                    for operand in (aa, bb):
                        for j in range(1, d):
                            basis.add_scaled(b, operand[j], operand[0], f.pow(point, j))
                    a, c = aa[0], bb[0]
                else:
                    a, c = aa[-1], bb[-1]
                pivot = next(i for i, w in enumerate(weights) if w)
                wp = weights[pivot]
                # Conjugate an update of cc[pivot] into the full output
                # interpolation vector. All constant field maps are linear.
                for j, w in enumerate(weights):
                    if j != pivot:
                        basis.add_scaled(b, cc[pivot], cc[j], f.div(w, wp))
                b.gf2_idiv(wp, target=cc[pivot], field=f)
                if h == 3:
                    self._mul8(a, c, cc[pivot])
                else:
                    b.ixor_gf2_mul(a, c, target=cc[pivot], field=f)
                b.gf2_imul(wp, target=cc[pivot], field=f)
                for j, w in enumerate(weights):
                    if j != pivot:
                        basis.add_scaled(b, cc[pivot], cc[j], f.div(w, wp))
                if point is not None:
                    for operand in (bb, aa):
                        for j in reversed(range(1, d)):
                            basis.add_scaled(b, operand[j], operand[0], f.pow(point, j))
            for reg in (target, rhs, lhs):
                basis.change_basis(b, reg, to_cubic=False)




