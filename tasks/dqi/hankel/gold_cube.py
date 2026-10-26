# SPDX-License-Identifier: Apache-2.0
# Port of SomeJoint v7; see PROVENANCE.md and SOURCE_MAP.json.
# Praxen: package imports; production functions only; no notebook runtime.
'Zero-scratch reversible XOR of a checked GF4096 cube.\n\nNew Hermitian-norm specialization; polynomial modulus 0x1053. The circuit\nuses the checked, fixed 26-AND data file, not the live heuristic output.'
from __future__ import annotations

from functools import cache
import json
from pathlib import Path


@cache
def data():
    result = json.loads(Path(__file__).with_name("hermitian12-search-check.json").read_text())
    assert result["degree"] == 12 and result["power"] == 3
    assert result["failures"] == 0 and result["truth_table_inputs"] == 4096
    return result


def xor_cube(b, source, target):
    """target ^= source**3; source and arbitrary target are disjoint words."""
    assert len(source) == len(target) == 12
    for u, v, weight in data()["terms"]:
        # First parity U in p; express V in the resulting coordinates.
        p = (u & -u).bit_length() - 1
        first = [(i, p) for i in range(12) if i != p and u >> i & 1]
        transformed_v = v ^ ((u ^ (1 << p)) if v >> p & 1 else 0)
        eligible = transformed_v & ~(1 << p)
        assert eligible
        q = (eligible & -eligible).bit_length() - 1
        second = [(i, q) for i in range(12) if i != q and transformed_v >> i & 1]
        r = (weight & -weight).bit_length() - 1
        output = [i for i in range(12) if i != r and weight >> i & 1]
        for i, j in first + second:
            b.cx(source[i], source[j])
        for i in output:
            b.cx(target[r], target[i])
        b.ccx(source[p], source[q], target[r])
        for i in reversed(output):
            b.cx(target[r], target[i])
        for i, j in reversed(first + second):
            b.cx(source[i], source[j])
    for i, column in enumerate(data()["linear_columns"]):
        for j in range(12):
            if column >> j & 1:
                b.cx(source[i], target[j])
