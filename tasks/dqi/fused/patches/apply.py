# SPDX-License-Identifier: Apache-2.0
"""Apply the active hengck23 edit modules onto a scratch source tree."""
from __future__ import annotations

from pathlib import Path

from . import e001_phase_zero_condition
from . import e002_projective_extract
from . import e011_clear_flag_by_measurement

# Ordered. Enable one at a time while measuring ΔT against EDIT_TRANSCRIPT.md.
ACTIVE_EDITS = (
    e001_phase_zero_condition,
    e011_clear_flag_by_measurement,
)

# e002 is value+phase correct but costs more than the baseline (Q 1513, mean T
# +35.8k vs hengck23's -15.3k), so it stays out of the shipped set.
# See docs/decisions/D-PRA322-02.md. Opt in with ``apply_patches(tree, experimental=True)``.
EXPERIMENTAL_EDITS = (
    e002_projective_extract,
)


def apply_patches(tree: Path, *, experimental: bool = False) -> list[dict]:
    tree = Path(tree)
    if not (tree / 'exp/decoder/build.py').is_file():
        raise SystemExit(f'patch tree missing build.py: {tree}')
    receipts = []
    for edit in ACTIVE_EDITS + (EXPERIMENTAL_EDITS if experimental else ()):
        receipts.append(edit.apply(tree))
    return receipts
