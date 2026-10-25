# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""42-Toffoli GF(4096) products and a 66-Toffoli inverse.

Use a quartic extension over GF(8) for full products and a cubic extension
over GF(4) for the GF(64) products inside the quadratic-tower inverse.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from .common import build  # noqa: E402
from .sweep import ReducedSweepDecoder  # noqa: E402
from .cubic import CubicBuilder  # noqa: E402


class EvaluationBuilder(CubicBuilder):
    def __init__(self):
        super().__init__(decompositions=((6, 2), (12, 3)))




