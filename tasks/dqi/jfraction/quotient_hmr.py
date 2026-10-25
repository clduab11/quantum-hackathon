# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Clear the second EEA quotient by HMR and a product-phase correction."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from .common import build  # noqa: E402
from .sweep import ReducedSweepDecoder  # noqa: E402
from .quotient import ControlledQuotientBuilder, _QuotientBuilder  # noqa: E402
from .forney_control import ControlledForneyDecoder  # noqa: E402


class MeasuredQuotientBuilder(ControlledQuotientBuilder):
    def clear_controlled_div(self, lhs, rhs, *, target, control, field):
        """Clear target, assuming it equals control * lhs/rhs on entry."""
        assert len(lhs) == len(rhs) == len(target) == 12 and field.modulus == 0x1053
        b = self.native
        with b.mark('clear_quotient_by_hmr'):
            mask = b.alloc_bits(12)
            b.hmr(target, mask)
            inverse, chain = self.init_controlled_inverse(rhs, control, target=target)
            b.gf2_phase_by_product(lhs, inverse, mask=mask, field=field)
            self.del_controlled_inverse(rhs, control, target=inverse, scaffold=chain)
            # target is the caller's q_i register; its later free remains imported.
            b.free(chain)
            b.free(mask)


class _MeasuredQuotientCopy(_QuotientBuilder):
    def __init__(self, builder):
        super().__init__(builder)
        self.accumulator = None

    def gf2_iadd(self, value, *, target, field=None, control=True):
        if self.pending is None or value is not self.pending[3]:
            return super().gf2_iadd(value, target=target, field=field, control=control)
        if self.completed == 0:
            assert self.accumulator is None
            self.accumulator = target
            return super().gf2_iadd(value, target=target, field=field, control=control)
        assert self.completed == 1 and target is self.accumulator
        lhs, rhs, saved_field, ratio, scaffold, done = self.pending
        assert not done and field.modulus == saved_field.modulus
        self.builder.clear_controlled_div(lhs, rhs, target=target, control=control, field=field)
        self.pending = (lhs, rhs, saved_field, ratio, scaffold, True)


class MeasuredQuotientDecoder(ControlledForneyDecoder):
    def _multiply_and_add_or_sub(self, builder, reg_a, reg_b, n_A, n_a, n_q,
                                 ctrl, it, *, is_adjoint):
        proxy = _MeasuredQuotientCopy(builder)
        # Reuse the v4 imported sweep with this quotient adapter, replacing v10's.
        ReducedSweepDecoder._multiply_and_add_or_sub(
            self, proxy, reg_a, reg_b, n_A, n_a, n_q, ctrl, it, is_adjoint=is_adjoint)
        assert proxy.pending is None and proxy.completed == 2




