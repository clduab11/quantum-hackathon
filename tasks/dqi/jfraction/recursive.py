# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""GF(4096) -> GF(64) -> GF(8) arithmetic with six-AND GF(8) multiplication.

The imported reference decoder and its iteration count are unchanged.
Run: python dqi/recursive.py /tmp/quantum-decoder/v2.kmb
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from .common import build, km  # noqa: E402
from .tower import QuadraticBasis, TowerBuilder  # noqa: E402


class RecursiveBuilder(TowerBuilder):
    def __init__(self):
        self.native = km.CircuitBuilder()
        self.bases = {n: QuadraticBasis(n) for n in (6, 12)}
        self.basis = self.bases[12]

    @staticmethod
    def _supported(field, width):
        return width in (3, 6, 12) and (
            field is None or field.modulus == {3: 0xb, 6: 0x43, 12: 0x1053}[width])

    def _mul8(self, lhs, rhs, target):
        """Accumulate a GF(8) product: 6 CCX, 16 CX, no scratch."""
        b = self.native

        def term(a, c, weight):
            bits = [i for i in range(3) if weight >> i & 1]
            pivot = bits[0]
            for i in bits[1:]:
                b.cx(target[pivot], target[i])
            b.ccx(a, c, target[pivot])
            for i in reversed(bits[1:]):
                b.cx(target[pivot], target[i])

        # The six rank-one terms omit input mask 6. The input cycle restores
        # both operands; output conjugation works for any initial target.
        term(lhs[0], rhs[0], 4)  # mask 1
        term(lhs[1], rhs[1], 6)  # mask 2
        term(lhs[2], rhs[2], 2)  # mask 4
        for source, weight in ((1, 1), (2, 3), (1, 7), (2, None)):
            b.cx(lhs[source], lhs[0])
            b.cx(rhs[source], rhs[0])
            if weight is not None:
                term(lhs[0], rhs[0], weight)  # masks 3, 7, 5

    def _multiply(self, lhs, rhs, target):
        """Uncontrolled product XOR, recursively in a quadratic tower."""
        n = len(lhs)
        if n == 3:
            self._mul8(lhs, rhs, target)
            return
        b, basis = self.native, self.bases[n]
        h = n // 2
        for reg in (lhs, rhs, target):
            basis.change_basis(b, reg, to_tower=True)
        a0, a1, b0, b1 = lhs[:h], lhs[h:], rhs[:h], rhs[h:]
        c0, c1 = target[:h], target[h:]
        # c0 ^= v0 + delta*v1; c1 ^= v0 + v2,
        # v0=a0*b0, v1=a1*b1, v2=(a0+a1)*(b0+b1).
        b.cx(c0, c1)
        self._multiply(a0, b0, c0)
        b.cx(c0, c1)
        b.gf2_idiv(basis.delta, target=c0, field=basis.inner)
        self._multiply(a1, b1, c0)
        b.gf2_imul(basis.delta, target=c0, field=basis.inner)
        b.cx(a0, a1)
        b.cx(b0, b1)
        self._multiply(a1, b1, c1)
        b.cx(b0, b1)
        b.cx(a0, a1)
        for reg in (target, rhs, lhs):
            basis.change_basis(b, reg, to_tower=False)

    def ixor_gf2_mul(self, lhs, rhs, *, target, field=None, control=True):
        if not self._supported(field, len(lhs)):
            return self.native.ixor_gf2_mul(lhs, rhs, target=target, field=field, control=control)
        if control is False:
            return
        b = self.native
        with b.mark('tower_multiply'):
            if control is True:
                self._multiply(lhs, rhs, target)
            elif isinstance(control, km.b):
                b.push_condition(control)
                self._multiply(lhs, rhs, target)
                b.pop_condition()
            else:
                # Linearity in lhs gives control*(lhs*rhs). The temporary
                # logical ANDs have free HMR deletion after the product.
                masked = b.alloc_qubits(len(lhs))
                b.init_and(control, lhs, masked)
                self._multiply(masked, rhs, target)
                b.del_and(control, lhs, masked)
                b.free(masked)

    def init_gf2_mul(self, lhs, rhs, *, target='alloc', field=None, control=True):
        out = self.native.alloc_qubits(len(lhs)) if isinstance(target, str) and target == 'alloc' else target
        self.native.reset(out)
        self.ixor_gf2_mul(lhs, rhs, target=out, field=field, control=control)
        return out

    def init_gf2_inverse_with_scaffold(self, input, *, target='alloc', field=None):
        n = len(input)
        if not self._supported(field, n):
            return self.native.init_gf2_inverse_with_scaffold(input, target=target, field=field)
        b = self.native
        out = b.alloc_qubits(n) if isinstance(target, str) and target == 'alloc' else target
        b.reset(out)
        if n == 3:
            with b.mark('inverse8'):
                # y0=x0+x1+x2+x1*x2, y1=x2+x0*x1, y2=x1+x2+x0*x2.
                b.cx(km.array([input[0], input[1], input[2], input[2], input[1], input[2]]),
                     km.array([out[0], out[0], out[0], out[1], out[2], out[2]]))
                b.ccx(input[1], input[2], out[0])
                b.ccx(input[0], input[1], out[1])
                b.ccx(input[0], input[2], out[2])
            return out, km.array([])
        basis, h = self.bases[n], n // 2
        with b.mark('recursive_inverse'):
            basis.change_basis(b, input, to_tower=True)
            a, c = input[:h], input[h:]
            norm = self.init_gf2_mul(a, c, field=basis.inner)
            basis.add_linear(b, a, norm, basis.square_columns)
            basis.add_linear(b, c, norm, basis.delta_square_columns)
            reciprocal, chain = self.init_gf2_inverse_with_scaffold(norm, field=basis.inner)
            self.init_gf2_mul(a, reciprocal, target=out[:h], field=basis.inner)
            self.init_gf2_mul(c, reciprocal, target=out[h:], field=basis.inner)
            b.cx(out[h:], out[:h])
            basis.change_basis(b, out, to_tower=False)
            basis.change_basis(b, input, to_tower=False)
        return out, norm + reciprocal + chain

    def del_gf2_inverse_with_scaffold(self, input, *, target, scaffold, field=None):
        n = len(input)
        if not self._supported(field, n):
            return self.native.del_gf2_inverse_with_scaffold(
                input, target=target, scaffold=scaffold, field=field)
        b = self.native
        if n == 3:
            assert len(scaffold) == 0
            with b.mark('uncompute_inverse8'):
                measured = b.alloc_bits(3)
                b.hmr(target, measured)
                # The same ANF, now as a phase polynomial selected by HMR bits.
                b.cz(km.array([measured[0], measured[0], measured[0], measured[1], measured[2], measured[2]]),
                     km.array([input[0], input[1], input[2], input[2], input[1], input[2]]))
                b.ccz(measured[0], input[1], input[2])
                b.ccz(measured[1], input[0], input[1])
                b.ccz(measured[2], input[0], input[2])
                b.free(measured)
            return
        basis, h = self.bases[n], n // 2
        with b.mark('uncompute_recursive_inverse'):
            norm, reciprocal, chain = scaffold[:h], scaffold[h:n], scaffold[n:]
            basis.change_basis(b, input, to_tower=True)
            basis.change_basis(b, target, to_tower=True)
            a, c = input[:h], input[h:]
            b.cx(target[h:], target[:h])
            b.del_gf2_mul(a, reciprocal, target=target[:h], field=basis.inner)
            b.del_gf2_mul(c, reciprocal, target=target[h:], field=basis.inner)
            self.del_gf2_inverse_with_scaffold(norm, target=reciprocal, scaffold=chain, field=basis.inner)
            basis.add_linear(b, c, norm, basis.delta_square_columns)
            basis.add_linear(b, a, norm, basis.square_columns)
            b.del_gf2_mul(a, c, target=norm, field=basis.inner)
            basis.change_basis(b, input, to_tower=False)

    def init_gf2_div_with_scaffold(self, lhs, rhs, *, target='alloc', field=None):
        inverse, chain = self.init_gf2_inverse_with_scaffold(rhs, field=field)
        out = self.init_gf2_mul(lhs, inverse, target=target, field=field)
        return out, inverse + chain




