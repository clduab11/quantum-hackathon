# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Remove the redundant c0 remainder-range cursor from the imported EEA sweep.

In c0, coefficients in the gap are zero until q is stored, and q is zero
afterward. The c3 guard still protects the live stored quotient coefficients.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from .common import build, ref  # noqa: E402
from .narrow import NarrowBuilder  # noqa: E402


class _FullRangeCursor:
    """A constant c0 range has no quantum address or transition matches."""
    match_qubit = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def move_to(self, value):
        pass


class _SweepBuilder:
    def __init__(self, builder, remainder_pointer):
        self.builder = builder
        self.remainder_pointer = remainder_pointer
        self.replacements = 0

    def __getattr__(self, name):
        return getattr(self.builder, name)

    def unary_iteration(self, address, **kwargs):
        if address is self.remainder_pointer:
            self.replacements += 1
            return _FullRangeCursor()
        return self.builder.unary_iteration(address, **kwargs)


class ReducedSweepDecoder(ref.ProosAndZalkaDecoder):
    def _multiply_and_add_or_sub(self, builder, reg_a, reg_b, n_A, n_a, n_q,
                                 ctrl, it, *, is_adjoint):
        # Adapt the imported routine instead of copying competition source.
        # This hook is scoped to one synchronous build call. All other range
        # cursors and all quotient storage/uncomputation remain the reference.
        original_threshold = ref._xor_threshold

        def threshold(b, cursor, limit, target, control, value, *, at_least, lowest=0):
            if isinstance(cursor, _FullRangeCursor):
                assert at_least
                b.cx(control, target)
            else:
                original_threshold(b, cursor, limit, target, control, value,
                                   at_least=at_least, lowest=lowest)

        proxy = _SweepBuilder(builder, n_A)
        try:
            ref._xor_threshold = threshold
            super()._multiply_and_add_or_sub(proxy, reg_a, reg_b, n_A, n_a, n_q,
                                           ctrl, it, is_adjoint=is_adjoint)
        finally:
            ref._xor_threshold = original_threshold
        assert proxy.replacements == 1




