# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Decode with 35 fixed-position degree-one Euclidean divisions.

Remainders share storage with growing auxiliary polynomials. Unexpected
leading zeros stop the decoder; nonterminal degree jumps are deliberate
approximation failures, while paired reversal still restores every input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from .common import build, km, ref  # noqa: E402
from .zero_chain import _ZeroTestBuilder  # noqa: E402
from .forney_control import _ForneyBuilder  # noqa: E402
from .quotient_hmr import MeasuredQuotientBuilder  # noqa: E402


class StaticArithmeticBuilder(MeasuredQuotientBuilder):
    def alloc_qubits(self, width):
        # This architecture has no imported degree-pointer allocations.
        return self.native.alloc_qubits(width)


class _NaturalForneyBuilder:
    """Evaluate natural sigma/Omega coefficients at alpha**(-position)."""
    def __init__(self, builder, field):
        self.builder = builder
        self.field = field
        self.phase_calls = 0

    def __getattr__(self, name):
        return getattr(self.builder, name)

    def gf2_imul(self, value, **kwargs):
        # The imported scan walks positive powers; natural locator roots
        # use negative powers. Its final restoration is adapted below too.
        return self.builder.gf2_imul(self.field.div(1, value), **kwargs)

    def gf2_idiv(self, value, **kwargs):
        return self.builder.gf2_idiv(self.field.div(1, value), **kwargs)

    def gf2_phase_by_product(self, lhs, rhs, *, mask, field=None):
        # The imported odd-coefficient sum is x*sigma'(x), so multiply
        # Omega(x) by x to retain the natural Forney ratio Omega/sigma'.
        scale = self.field.pow(self.field.primitive_element,
                               -self.phase_calls % ((1 << self.field.degree) - 1))
        self.builder.gf2_imul(scale, target=lhs, field=self.field)
        self.builder.gf2_phase_by_product(lhs, rhs, mask=mask, field=field)
        self.builder.gf2_idiv(scale, target=lhs, field=self.field)
        self.phase_calls += 1


class StaticDivisionDecoder(ref.ProosAndZalkaDecoder):
    @staticmethod
    def _record(builder, name):
        circuit = builder.finish_circuit()
        stats = circuit.operation_statistics()
        previous = builder.stage_records[-1]['toffolis_cumulative'] if builder.stage_records else 0
        builder.stage_records.append({
            'boundary': name, 'toffolis_cumulative': stats.num_toffoli_like,
            'toffolis_since_previous': stats.num_toffoli_like - previous,
            'peak_qubits': circuit.num_qubits, 'live_qubits': builder.num_allocated_qubits,
            'ops_cumulative': len(circuit)})

    def _product(self, builder, lhs, rhs, target):
        builder.ixor_gf2_mul(lhs, rhs, target=target, field=self.field)

    def _division_round(self, builder, a, b, j, active, *, is_adjoint):
        """Update b by a linear quotient; quotient bits are zero on exit."""
        d = 69 - j
        q1, q0 = builder.alloc_qubits(12), builder.alloc_qubits(12)

        def quotient(lhs, rhs, target, clear=False):
            method = builder.clear_controlled_div if clear else builder.ixor_controlled_div
            method(lhs, rhs, target=target, control=active, field=self.field)

        def remainder(q, shift):
            for i in range(d + 1):
                self._product(builder, q, a[i], b[i + shift])

        def auxiliary(q, shift):
            for i in range(j + 1):
                self._product(builder, q, a[70 - i], b[70 - i - shift])

        def lower_quotient(clear=False):
            if j:
                self._product(builder, q1, a[d + 2], b[d + 1])
            quotient(b[d + 1], a[d + 1], q0, clear)
            if j:
                self._product(builder, q1, a[d + 2], b[d + 1])

        with builder.mark('static_division_reverse' if is_adjoint else 'static_division'):
            if not is_adjoint:
                quotient(b[d + 1], a[d], q1)
                remainder(q1, 1)
                quotient(b[d], a[d], q0)
                remainder(q0, 0)
                auxiliary(q1, 1)
                auxiliary(q0, 0)
                lower_quotient(clear=True)
                quotient(b[d], a[d + 1], q1, clear=True)
            else:
                quotient(b[d], a[d + 1], q1)
                lower_quotient()
                auxiliary(q0, 0)
                auxiliary(q1, 1)
                remainder(q0, 0)
                quotient(b[d], a[d], q0, clear=True)
                remainder(q1, 1)
                quotient(b[d + 1], a[d], q1, clear=True)
        builder.free(q0 + q1)

    @staticmethod
    def _next_active(builder, coefficient, previous, target, *, is_adjoint):
        if is_adjoint:
            builder.cx(previous, target)
        builder.flip_if_equal(coefficient, 0, target=target, control=previous)
        if not is_adjoint:
            builder.cx(previous, target)

    def _pre_align_reg_b(self, builder, reg_b, n_b, n_B, *, is_adjoint):
        # The view already has fixed natural coefficient positions.
        pass

    def _natural_forney(self, builder, bank, error_mbuc):
        unused = km.array([])
        # Preserve the imported scan's indices without allocating its two
        # unused separators: sigma[0..35], gap, Omega[34..0], gap.
        layout = list(reversed(bank[35:71])) + [unused] + list(reversed(bank[:35])) + [unused]
        assert len(layout) == 73
        natural = _NaturalForneyBuilder(builder, self.field)
        forney = _ForneyBuilder(natural)
        zero = _ZeroTestBuilder(forney, layout[0])
        ref.ProosAndZalkaDecoder._chien_search_and_forney_mbuc(
            self, zero, layout, error_mbuc, 0, 0)
        assert natural.phase_calls == forney.products == 4095
        assert forney.header_allocations == 3 and forney.omega is None
        assert zero.chain is None and zero.calls == 8190

    def build_syndrome_decoding_mbuc(self, builder, *, syndromes, error_mbuc, n_iters):
        assert n_iters == 35 and len(syndromes) == 70 and len(error_mbuc) == 4095
        assert self.field.degree == 12 and self.field.modulus == 0x1053
        builder.stage_records = []
        a_tail = builder.alloc_qubits(12)
        a = list(syndromes) + [a_tail]
        b = [builder.alloc_qubits(12) for _ in range(71)]
        active = builder.alloc_qubits(35)
        builder.x(km.array([a_tail[0], b[70][0], active[0]]))
        builder.flip_if_equal(syndromes[69], 0, target=active[0])
        self._record(builder, 'initialization')

        with builder.mark('forward_static_divisions'):
            for j in range(35):
                lhs, rhs = (a, b) if j % 2 == 0 else (b, a)
                self._division_round(builder, lhs, rhs, j, active[j], is_adjoint=False)
                if j < 34:
                    self._next_active(builder, rhs[68 - j], active[j], active[j + 1],
                                      is_adjoint=False)
        self._record(builder, 'forward_key_equation')

        choose_b = builder.alloc_qubits(1)[0]
        builder.cx(active, choose_b)
        flat_a = km.array([q for word in a for q in word])
        flat_b = km.array([q for word in b for q in word])
        builder.cswap(choose_b, flat_a, flat_b)
        self._record(builder, 'select_pair')
        self._natural_forney(builder, a, error_mbuc)
        self._record(builder, 'phase_correction')
        builder.cswap(choose_b, flat_a, flat_b)
        builder.cx(active, choose_b)
        builder.free(choose_b)
        self._record(builder, 'unselect_pair')

        with builder.mark('reverse_static_divisions'):
            for j in reversed(range(35)):
                lhs, rhs = (a, b) if j % 2 == 0 else (b, a)
                if j < 34:
                    self._next_active(builder, rhs[68 - j], active[j], active[j + 1],
                                      is_adjoint=True)
                self._division_round(builder, lhs, rhs, j, active[j], is_adjoint=True)
        self._record(builder, 'reverse_key_equation')

        builder.flip_if_equal(syndromes[69], 0, target=active[0])
        builder.x(km.array([a_tail[0], b[70][0], active[0]]))
        builder.free(active + a_tail + km.array([q for word in b for q in word]))
        self._record(builder, 'cleanup')




