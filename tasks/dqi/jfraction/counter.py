# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Use six bits for a halting counter that advances at most every fourth step."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from .common import build  # noqa: E402
from .evaluation import EvaluationBuilder  # noqa: E402
from .zero_chain import ZeroChainDecoder  # noqa: E402


class CompactCounterBuilder(EvaluationBuilder):
    def __init__(self):
        super().__init__()
        self.halting_allocations = 0

    def alloc_qubits(self, width):
        if width == 8 and self.pointer_allocations == 5 and not self.halting_allocations:
            self.halting_allocations += 1
            return self.native.alloc_qubits(6)
        return super().alloc_qubits(width)




