# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Replace GF(4096) inversion by a quadratic norm over GF(64).

The EEA, Chien search, phase correction and cleanup are imported from the
competition reference. Only the inverse and its division wrapper change.
Run: python dqi/tower.py /tmp/quantum-decoder/v1.kmb
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from .common import build, km  # noqa: E402


def xor_columns(columns, value):
    result = 0
    for bit, column in enumerate(columns):
        if value >> bit & 1:
            result ^= column
    return result


def elimination_gates(columns):
    """CNOT/SWAP gates mapping the columns' basis back to the standard basis."""
    n = len(columns)
    rows = [sum(((column >> i) & 1) << j for j, column in enumerate(columns)) for i in range(n)]
    gates = []
    for i in range(n):
        pivot = next(j for j in range(i, n) if rows[j] >> i & 1)
        if pivot != i:
            rows[i], rows[pivot] = rows[pivot], rows[i]
            gates.append(('swap', i, pivot))
        for j in range(n):
            if j != i and rows[j] >> i & 1:
                rows[j] ^= rows[i]
                gates.append(('cx', i, j))
    assert rows == [1 << i for i in range(n)]
    return gates


class QuadraticBasis:
    """Deterministic quadratic extension, with theta^2+theta=delta."""

    def __init__(self, degree=12):
        assert degree in (6, 12)
        half = degree // 2
        self.outer = km.GF2Field(degree)
        self.inner = km.GF2Field(half)
        f = self.outer

        def evaluate_modulus(value):
            total = 0
            for power in range(half + 1):
                if self.inner.modulus >> power & 1:
                    total ^= f.pow(value, power)
            return total

        beta = next(x for x in range(2, 1 << degree) if evaluate_modulus(x) == 0)
        embedded = [f.pow(beta, i) for i in range(half)]
        reverse = {xor_columns(embedded, x): x for x in range(1 << half)}
        theta = next(x for x in range(2, 1 << degree) if x ^ f.pow(x, 1 << half) == 1)
        self.delta = reverse[f.square(theta) ^ theta]
        self.columns = embedded + [f.mul(theta, e) for e in embedded]
        self.to_tower = elimination_gates(self.columns)
        self.square_columns = [self.inner.square(1 << i) for i in range(half)]
        self.delta_square_columns = [self.inner.mul(self.delta, x) for x in self.square_columns]
        self.beta, self.theta = beta, theta

    def change_basis(self, builder, wires, *, to_tower):
        gates = self.to_tower if to_tower else reversed(self.to_tower)
        for kind, a, b in gates:
            getattr(builder, kind)(wires[a], wires[b])

    @staticmethod
    def add_linear(builder, source, target, columns):
        for i, column in enumerate(columns):
            for j in range(len(target)):
                if column >> j & 1:
                    builder.cx(source[i], target[j])


class TowerBuilder:
    """Forward the reference builder API except the two inverse/division pairs."""

    def __init__(self):
        self.native = km.CircuitBuilder()
        self.basis = QuadraticBasis()

    def __getattr__(self, name):
        return getattr(self.native, name)

    def init_gf2_inverse_with_scaffold(self, input, *, target='alloc', field=None):
        if len(input) != 12 or (field is not None and field.modulus != self.basis.outer.modulus):
            return self.native.init_gf2_inverse_with_scaffold(input, target=target, field=field)
        b, basis = self.native, self.basis
        out = b.alloc_qubits(12) if isinstance(target, str) and target == 'alloc' else target
        with b.mark('tower_inverse'):
            b.reset(out)
            basis.change_basis(b, input, to_tower=True)
            a, c = input[:6], input[6:]
            # Norm(a+c*theta) = a^2 + a*c + delta*c^2.
            norm = b.init_gf2_mul(a, c, field=basis.inner)
            basis.add_linear(b, a, norm, basis.square_columns)
            basis.add_linear(b, c, norm, basis.delta_square_columns)
            reciprocal, chain = b.init_gf2_inverse_with_scaffold(norm, field=basis.inner)
            b.init_gf2_mul(a, reciprocal, target=out[:6], field=basis.inner)
            b.init_gf2_mul(c, reciprocal, target=out[6:], field=basis.inner)
            b.cx(out[6:], out[:6])
            basis.change_basis(b, out, to_tower=False)
            basis.change_basis(b, input, to_tower=False)
        return out, norm + reciprocal + chain

    def del_gf2_inverse_with_scaffold(self, input, *, target, scaffold, field=None):
        if len(input) != 12 or (field is not None and field.modulus != self.basis.outer.modulus):
            return self.native.del_gf2_inverse_with_scaffold(
                input, target=target, scaffold=scaffold, field=field)
        b, basis = self.native, self.basis
        with b.mark('uncompute_tower_inverse'):
            norm, reciprocal, chain = scaffold[:6], scaffold[6:12], scaffold[12:]
            basis.change_basis(b, input, to_tower=True)
            basis.change_basis(b, target, to_tower=True)
            a, c = input[:6], input[6:]
            b.cx(target[6:], target[:6])
            b.del_gf2_mul(a, reciprocal, target=target[:6], field=basis.inner)
            b.del_gf2_mul(c, reciprocal, target=target[6:], field=basis.inner)
            b.del_gf2_inverse_with_scaffold(norm, target=reciprocal, scaffold=chain, field=basis.inner)
            basis.add_linear(b, c, norm, basis.delta_square_columns)
            basis.add_linear(b, a, norm, basis.square_columns)
            b.del_gf2_mul(a, c, target=norm, field=basis.inner)
            basis.change_basis(b, input, to_tower=False)

    def init_gf2_div_with_scaffold(self, lhs, rhs, *, target='alloc', field=None):
        inverse, chain = self.init_gf2_inverse_with_scaffold(rhs, field=field)
        out = self.native.init_gf2_mul(lhs, inverse, target=target, field=field)
        return out, inverse + chain

    def del_gf2_div_with_scaffold(self, lhs, rhs, *, target, scaffold, field=None):
        inverse, chain = scaffold[:len(rhs)], scaffold[len(rhs):]
        self.native.del_gf2_mul(lhs, inverse, target=target, field=field)
        self.del_gf2_inverse_with_scaffold(rhs, target=inverse, scaffold=chain, field=field)




