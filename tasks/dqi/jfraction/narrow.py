# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Use seven bits for the five EEA pointers into 73-word arrays.

All field arithmetic is v2. The halting counter remains eight bits, and the
reference's 222 forward and reverse steps are unchanged.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from .common import build  # noqa: E402
from .recursive import RecursiveBuilder  # noqa: E402


class NarrowBuilder(RecursiveBuilder):
    def __init__(self):
        super().__init__()
        self.pointer_allocations = 0

    def alloc_qubits(self, width):
        # In the imported top-level builder, the first five 8-bit allocations
        # are n_A, n_B, n_a, n_b and n_q. The next is the halting counter.
        # Internal arithmetic uses self.native and does not pass this hook.
        if width == 8 and self.pointer_allocations < 5:
            self.pointer_allocations += 1
            return self.native.alloc_qubits(7)
        return self.native.alloc_qubits(width)




