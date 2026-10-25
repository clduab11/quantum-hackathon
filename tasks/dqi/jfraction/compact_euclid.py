# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Implicit-remainder Euclid in 70 syndrome plus 36 auxiliary field words.

Each active slot consumes one high syndrome cell for the previous auxiliary
polynomial. Missing leading coefficients halt approximately, as in v14.
All scratch and the input are restored, including on those halted paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from .common import build, km, ref
from .static_divisions import StaticArithmeticBuilder, StaticDivisionDecoder, _NaturalForneyBuilder
from .forney_control import _ForneyBuilder


class _EnabledZeroTest:
    """Retain the locator-zero AND chain, also requiring a valid constant."""
    def __init__(self, builder, sigma, enabled):
        self.builder, self.sigma, self.enabled = builder, sigma, enabled
        self.chain = None
        self.calls = 0

    def __getattr__(self, name):
        return getattr(self.builder, name)

    def flip_if_equal(self, lhs, rhs, *, target, control=True):
        if lhs is not self.sigma or rhs != 0 or control is not True:
            return self.builder.flip_if_equal(lhs, rhs, target=target, control=control)
        b = self.builder
        self.calls += 1
        b.x(lhs)
        if self.chain is None:
            self.chain = b.alloc_qubits(11)
            b.init_and(self.enabled, lhs[0], self.chain[0])
            for i in range(1, 11):
                b.init_and(self.chain[i - 1], lhs[i], self.chain[i])
            b.init_and(self.chain[-1], lhs[-1], target)
        else:
            b.del_and(self.chain[-1], lhs[-1], target)
            for i in reversed(range(1, 11)):
                b.del_and(self.chain[i - 1], lhs[i], self.chain[i])
            b.del_and(self.enabled, lhs[0], self.chain[0])
            b.free(self.chain)
            self.chain = None
        b.x(lhs)


class CompactEuclidDecoder(StaticDivisionDecoder):
    @staticmethod
    def _flatten(words):
        return km.array([q for word in words for q in word])

    def _phase_product(self, b, lhs, rhs, mask, *, control=True):
        if control is True:
            b.gf2_phase_by_product(lhs, rhs, mask=mask, field=self.field)
        elif control is not False:
            masked = b.alloc_qubits(12)
            b.init_and(control, lhs, masked)
            b.gf2_phase_by_product(masked, rhs, mask=mask, field=self.field)
            b.del_and(control, lhs, masked)
            b.free(masked)

    def _product_controlled(self, b, lhs, rhs, target, control=True):
        b.ixor_gf2_mul(lhs, rhs, target=target, control=control, field=self.field)

    def _dot(self, b, s, poly, d, target, *, control=True, mask=None):
        for i, word in enumerate(poly):
            assert d - i >= 0
            if mask is None:
                self._product_controlled(b, word, s[d - i], target, control)
            else:
                self._phase_product(b, word, s[d - i], mask, control=control)

    def _clear_dot(self, b, s, poly, d, target):
        mask = b.alloc_bits(12)
        b.hmr(target, mask)
        self._dot(b, s, poly, d, None, mask=mask)
        b.free(mask)

    @staticmethod
    def _halt(b, halt, a, j, *, reverse):
        stop = b.alloc_qubits(1)[0]
        if reverse:
            b.flip_if_equal(halt, j + 1, target=stop)
        else:
            b.flip_if_equal(halt + a, 0, target=stop)
        for bit in range(6):
            if (j + 1) >> bit & 1:
                b.cx(stop, halt[bit])
        if reverse:
            b.flip_if_equal(halt + a, 0, target=stop)
        else:
            b.flip_if_equal(halt, j + 1, target=stop)
        b.free(stop)

    def _quotient(self, b, lhs, rhs, target, active, *, clear=False):
        fn = b.clear_controlled_div if clear else b.ixor_controlled_div
        fn(lhs, rhs, target=target, control=active, field=self.field)

    def _q0_from_w(self, b, s, c, h, r, j, carry, q0, active, *, clear):
        w = h[:j] + [r, c[j + 1]]
        numerator = b.alloc_qubits(12)
        self._dot(b, s, w, 69 - j, numerator)
        self._quotient(b, numerator, carry, q0, active, clear=clear)
        self._clear_dot(b, s, w, 69 - j, numerator)
        b.free(numerator)

    def _q0_from_top(self, b, c, h, j, q1, q0, active, *, clear):
        if j:
            self._product(b, q1, h[j - 1], c[j])
        self._quotient(b, c[j], h[j], q0, active, clear=clear)
        if j:
            self._product(b, q1, h[j - 1], c[j])

    def _erase_syndrome(self, b, s, c, h, r, j, carry, q0, active):
        """Toggle S_d by its reconstruction, before the auxiliary swap.

        W=V+q1*z*U is already prepared. If U0=0, W0=V0 is nonzero;
        routing the two polynomials makes the same convolution usable.
        """
        d = 69 - j
        pivot = b.alloc_qubits(1)[0] if j else False

        def route():
            if j:
                b.cswap(pivot, self._flatten(c[:j]), self._flatten(h[:j]))
                b.cswap(pivot, c[j], r)

        if j:
            b.flip_if_equal(c[0], 0, target=pivot, control=active)
        route()
        numerator = b.alloc_qubits(12)
        b.cx(carry, numerator)
        if j:
            for src, dst in zip(carry, numerator):
                b.ccx(pivot, src, dst)
            self._product_controlled(b, q0, carry, numerator, pivot)
        for i in range(1, j + 1):
            self._product(b, c[i], s[d - i], numerator)
        if j:
            self._product_controlled(b, c[j + 1], s[d - j - 1], numerator, pivot)
        self._quotient(b, numerator, c[0], h[j], active)

        mask = b.alloc_bits(12)
        b.hmr(numerator, mask)
        b.cz(mask, carry)
        if j:
            for measured, word_bit in zip(mask, carry):
                b.ccz(measured, pivot, word_bit)
            self._phase_product(b, q0, carry, mask, control=pivot)
        for i in range(1, j + 1):
            self._phase_product(b, c[i], s[d - i], mask)
        if j:
            self._phase_product(b, c[j + 1], s[d - j - 1], mask, control=pivot)
        b.free(mask + numerator)
        route()
        if j:
            b.flip_if_equal(c[0], 0, target=pivot, control=active)
            b.free(pivot)

    def _forward_round(self, b, s, c, carry, halt, j):
        d, h = 69 - j, list(reversed(s))
        a = b.alloc_qubits(12)
        self._dot(b, s, c[:j + 1], d, a)
        self._halt(b, halt, a, j, reverse=False)
        active = b.alloc_qubits(1)[0]
        b.flip_if_equal(halt, 0, target=active)
        q1, q0 = b.alloc_qubits(12), b.alloc_qubits(12)
        self._quotient(b, carry, a, q1, active)

        # Transfer the new leading remainder to carry, deleting the old lead.
        b.cswap(active, carry, a)
        mask = b.alloc_bits(12)
        b.hmr(a, mask)
        self._phase_product(b, q1, carry, mask)
        b.x(active)
        self._dot(b, s, c[:j + 1], d, None, control=active, mask=mask)
        b.x(active)
        b.free(mask + a)

        # W=V+q1*z*U: its lower cells reuse H; the top two are separate.
        r = b.alloc_qubits(12)
        for i in range(1, j):
            self._product(b, q1, c[i - 1], h[i])
        if j:
            self._product(b, q1, c[j - 1], r)
        self._product(b, q1, c[j], c[j + 1])
        self._q0_from_w(b, s, c, h, r, j, carry, q0, active, clear=False)
        self._erase_syndrome(b, s, c, h, r, j, carry, q0, active)

        b.cswap(active, self._flatten(c[:j + 1]), self._flatten(h[:j + 1]))
        b.cx(r, c[j])
        if j:
            b.del_gf2_mul(q1, h[j - 1], target=r, field=self.field)
        b.free(r)
        for i in range(j + 1):
            self._product(b, q0, h[i], c[i])
        self._q0_from_top(b, c, h, j, q1, q0, active, clear=True)
        self._quotient(b, c[j + 1], h[j], q1, active, clear=True)
        b.free(q0 + q1)
        b.flip_if_equal(halt, 0, target=active)
        b.free(active)

    def _reverse_round(self, b, s, c, carry, halt, j):
        d, h = 69 - j, list(reversed(s))
        active = b.alloc_qubits(1)[0]
        b.flip_if_equal(halt, 0, target=active)
        q1, q0 = b.alloc_qubits(12), b.alloc_qubits(12)
        self._quotient(b, c[j + 1], h[j], q1, active)
        self._q0_from_top(b, c, h, j, q1, q0, active, clear=False)
        for i in range(j + 1):
            self._product(b, q0, h[i], c[i])
        r = b.alloc_qubits(12)
        if j:
            self._product(b, q1, h[j - 1], r)
        b.cx(r, c[j])
        b.cswap(active, self._flatten(c[:j + 1]), self._flatten(h[:j + 1]))
        self._erase_syndrome(b, s, c, h, r, j, carry, q0, active)
        self._q0_from_w(b, s, c, h, r, j, carry, q0, active, clear=True)
        b.free(q0)
        b.del_gf2_mul(q1, c[j], target=c[j + 1], field=self.field)
        if j:
            b.del_gf2_mul(q1, c[j - 1], target=r, field=self.field)
        b.free(r)
        for i in range(1, j):
            self._product(b, q1, c[i - 1], h[i])

        a = b.alloc_qubits(12)
        self._product(b, q1, carry, a)
        b.x(active)
        self._dot(b, s, c[:j + 1], d, a, control=active)
        b.x(active)
        b.cswap(active, carry, a)
        self._quotient(b, carry, a, q1, active, clear=True)
        b.free(q1)
        b.flip_if_equal(halt, 0, target=active)
        b.free(active)
        self._halt(b, halt, a, j, reverse=True)
        self._clear_dot(b, s, c[:j + 1], d, a)
        b.free(a)

    def _scale(self, b, word, factor, *, divide):
        """In-place multiply/divide by a promised nonzero variable factor."""
        temp = b.alloc_qubits(12)
        if divide:
            self._quotient(b, word, factor, temp, True)
        else:
            self._product(b, word, factor, temp)
        b.swap(word, temp)
        if divide:
            b.del_gf2_mul(word, factor, target=temp, field=self.field)
        else:
            self._quotient(b, word, factor, temp, True, clear=True)
        b.free(temp)

    def _omega(self, b, s, c, *, reverse):
        for k in (range(35) if reverse else reversed(range(35))):
            if not reverse:
                self._scale(b, s[k], c[0], divide=False)
            for i in range(1, k + 1):
                self._product(b, c[i], s[k - i], s[k])
            if reverse:
                self._scale(b, s[k], c[0], divide=True)

    def _forney(self, b, s, c, enabled, outcomes):
        unused = km.array([])
        layout = c + [unused] + list(reversed(s[:35])) + [unused]
        natural = _NaturalForneyBuilder(b, self.field)
        forney = _ForneyBuilder(natural)
        zero = _EnabledZeroTest(forney, c[0], enabled)
        ref.ProosAndZalkaDecoder._chien_search_and_forney_mbuc(
            self, zero, layout, outcomes, 0, 0)
        assert natural.phase_calls == forney.products == 4095
        assert zero.chain is None and zero.calls == 8190

    def build_syndrome_decoding_mbuc(self, builder, *, syndromes, error_mbuc, n_iters):
        assert n_iters == 35 and len(syndromes) == 70 and len(error_mbuc) == 4095
        assert self.field.degree == 12 and self.field.modulus == 0x1053
        b, s = builder, list(syndromes)
        b.stage_records = []
        c = [b.alloc_qubits(12) for _ in range(36)]
        carry, halt = b.alloc_qubits(12), b.alloc_qubits(6)
        b.x(km.array([c[0][0], carry[0]]))
        self._record(b, 'initialization')
        for j in range(35):
            with b.mark('compact_forward_round'):
                self._forward_round(b, s, c, carry, halt, j)
        self._record(b, 'forward_key_equation')

        enabled = b.alloc_qubits(1)[0]
        b.x(enabled)
        b.flip_if_equal(c[0], 0, target=enabled)
        b.x(enabled)
        b.cx(enabled, c[0][0])
        b.x(enabled)
        self._omega(b, s, c, reverse=False)
        self._record(b, 'evaluator_transform')
        self._forney(b, s, c, enabled, error_mbuc)
        self._record(b, 'phase_correction')
        self._omega(b, s, c, reverse=True)
        b.x(enabled)
        b.cx(enabled, c[0][0])
        b.x(enabled)
        b.flip_if_equal(c[0], 0, target=enabled)
        b.x(enabled)
        b.free(enabled)
        self._record(b, 'inverse_evaluator_transform')

        for j in reversed(range(35)):
            with b.mark('compact_reverse_round'):
                self._reverse_round(b, s, c, carry, halt, j)
        self._record(b, 'reverse_key_equation')
        b.x(km.array([c[0][0], carry[0]]))
        b.free(self._flatten(c) + carry + halt)
        self._record(b, 'cleanup')




