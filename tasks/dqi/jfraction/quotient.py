# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Accumulate controlled quotients directly, masking only the base reciprocal."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from .common import build, km  # noqa: E402
from .zero_chain import ZeroChainDecoder  # noqa: E402
from .counter import CompactCounterBuilder  # noqa: E402


class ControlledQuotientBuilder(CompactCounterBuilder):
    def init_controlled_inverse(self, input, control, *, target='alloc'):
        """Return control/input and a retained norm/reciprocal scaffold."""
        b, n = self.native, len(input)
        out = b.alloc_qubits(n) if isinstance(target, str) and target == 'alloc' else target
        b.reset(out)
        if n == 3:
            ordinary, chain = self.init_gf2_inverse_with_scaffold(input, field=km.GF2Field(3))
            assert not len(chain)
            b.init_and(control, ordinary, out)
            return out, ordinary
        basis, h = self.bases[n], n // 2
        with b.mark('controlled_recursive_inverse'):
            basis.change_basis(b, input, to_tower=True)
            a, c = input[:h], input[h:]
            norm = self.init_gf2_mul(a, c, field=basis.inner)
            basis.add_linear(b, a, norm, basis.square_columns)
            basis.add_linear(b, c, norm, basis.delta_square_columns)
            reciprocal, chain = self.init_controlled_inverse(norm, control)
            self.init_gf2_mul(a, reciprocal, target=out[:h], field=basis.inner)
            self.init_gf2_mul(c, reciprocal, target=out[h:], field=basis.inner)
            b.cx(out[h:], out[:h])
            basis.change_basis(b, out, to_tower=False)
            basis.change_basis(b, input, to_tower=False)
        return out, norm + reciprocal + chain

    def del_controlled_inverse(self, input, control, *, target, scaffold):
        b, n = self.native, len(input)
        if n == 3:
            assert len(scaffold) == 3
            b.del_and(control, scaffold, target)
            self.del_gf2_inverse_with_scaffold(input, target=scaffold, scaffold=km.array([]),
                                               field=km.GF2Field(3))
            return
        basis, h = self.bases[n], n // 2
        with b.mark('uncompute_controlled_recursive_inverse'):
            norm, reciprocal, chain = scaffold[:h], scaffold[h:n], scaffold[n:]
            basis.change_basis(b, input, to_tower=True)
            basis.change_basis(b, target, to_tower=True)
            a, c = input[:h], input[h:]
            b.cx(target[h:], target[:h])
            b.del_gf2_mul(a, reciprocal, target=target[:h], field=basis.inner)
            b.del_gf2_mul(c, reciprocal, target=target[h:], field=basis.inner)
            self.del_controlled_inverse(norm, control, target=reciprocal, scaffold=chain)
            basis.add_linear(b, c, norm, basis.delta_square_columns)
            basis.add_linear(b, a, norm, basis.square_columns)
            b.del_gf2_mul(a, c, target=norm, field=basis.inner)
            basis.change_basis(b, input, to_tower=False)

    def ixor_controlled_div(self, lhs, rhs, *, target, control, field):
        assert len(lhs) == len(rhs) == 12 and field.modulus == self.bases[12].outer.modulus
        inverse, chain = self.init_controlled_inverse(rhs, control)
        self.ixor_gf2_mul(lhs, inverse, target=target, field=field)
        self.del_controlled_inverse(rhs, control, target=inverse, scaffold=chain)
        self.native.free(inverse + chain)


class _QuotientBuilder:
    """Fuse one imported compute/copy/delete sequence without a ratio register."""

    def __init__(self, builder):
        self.builder = builder
        self.pending = None
        self.completed = 0

    def __getattr__(self, name):
        return getattr(self.builder, name)

    def init_gf2_div_with_scaffold(self, lhs, rhs, *, target='alloc', field=None):
        assert self.pending is None and target == 'alloc'
        ratio, scaffold = km.array([]), km.array([])
        self.pending = (lhs, rhs, field, ratio, scaffold, False)
        return ratio, scaffold

    def gf2_iadd(self, value, *, target, field=None, control=True):
        if self.pending is None or value is not self.pending[3]:
            return self.builder.gf2_iadd(value, target=target, field=field, control=control)
        lhs, rhs, saved_field, ratio, scaffold, done = self.pending
        assert not done and field.modulus == saved_field.modulus
        self.builder.ixor_controlled_div(lhs, rhs, target=target, control=control, field=field)
        self.pending = (lhs, rhs, saved_field, ratio, scaffold, True)

    def del_gf2_div_with_scaffold(self, lhs, rhs, *, target, scaffold, field=None):
        assert self.pending is not None
        a, c, f, ratio, saved_scaffold, done = self.pending
        assert done and lhs is a and rhs is c and target is ratio and scaffold is saved_scaffold
        assert field.modulus == f.modulus
        self.pending = None
        self.completed += 1


class DirectQuotientDecoder(ZeroChainDecoder):
    def _multiply_and_add_or_sub(self, builder, reg_a, reg_b, n_A, n_a, n_q,
                                 ctrl, it, *, is_adjoint):
        proxy = _QuotientBuilder(builder)
        super()._multiply_and_add_or_sub(proxy, reg_a, reg_b, n_A, n_a, n_q,
                                         ctrl, it, is_adjoint=is_adjoint)
        assert proxy.pending is None and proxy.completed == 2




