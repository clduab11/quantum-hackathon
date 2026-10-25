# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Keep the locator-zero AND chain across each Forney phase operation.

The 12-bit zero test costs 11 Toffolis including HMR cleanup, instead of
two 12-Toffoli equality toggles. Its ten retained scratch bits fit below
the EEA's existing peak qubit count.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from .common import build  # noqa: E402
from .evaluation import EvaluationBuilder  # noqa: E402
from .early_a import EarlyADecoder  # noqa: E402


class _ZeroTestBuilder:
    def __init__(self, builder, sigma):
        self.builder = builder
        self.sigma = sigma
        self.chain = None
        self.flag = None
        self.calls = 0

    def __getattr__(self, name):
        return getattr(self.builder, name)

    def flip_if_equal(self, lhs, rhs, *, target, control=True):
        if lhs is not self.sigma or rhs != 0 or control is not True:
            return self.builder.flip_if_equal(lhs, rhs, target=target, control=control)
        b = self.builder
        self.calls += 1
        with b.mark('retained_locator_zero_test'):
            b.x(lhs)
            if self.chain is None:
                self.chain = b.alloc_qubits(len(lhs) - 2)
                self.flag = target
                b.init_and(lhs[0], lhs[1], self.chain[0])
                for i in range(1, len(self.chain)):
                    b.init_and(self.chain[i-1], lhs[i+1], self.chain[i])
                b.init_and(self.chain[-1], lhs[-1], target)
            else:
                assert target == self.flag
                b.del_and(self.chain[-1], lhs[-1], target)
                for i in reversed(range(1, len(self.chain))):
                    b.del_and(self.chain[i-1], lhs[i+1], self.chain[i])
                b.del_and(lhs[0], lhs[1], self.chain[0])
                b.free(self.chain)
                self.chain = self.flag = None
            b.x(lhs)


class ZeroChainDecoder(EarlyADecoder):
    def _chien_search_and_forney_mbuc(self, builder, reg_b, error_mbuc, n_b, n_B):
        sigma = self.readout[0][0]
        proxy = _ZeroTestBuilder(builder, sigma)
        super()._chien_search_and_forney_mbuc(proxy, reg_b, error_mbuc, n_b, n_B)
        assert proxy.chain is None
        assert proxy.calls == 2 * min((1 << self.field.degree) - 1, len(error_mbuc))




