# SPDX-License-Identifier: Apache-2.0
"""Apply the active hengck23 edit modules onto a scratch source tree."""
from __future__ import annotations

from pathlib import Path

from . import e001_phase_zero_condition
from . import e002_projective_extract

# Ordered. Enable one at a time while measuring ΔT against EDIT_TRANSCRIPT.md.
ACTIVE_EDITS = (
    e001_phase_zero_condition,
    e002_projective_extract,
)


def apply_patches(tree: Path) -> list[dict]:
    tree = Path(tree)
    if not (tree / 'exp/decoder/build.py').is_file():
        raise SystemExit(f'patch tree missing build.py: {tree}')
    receipts = []
    for edit in ACTIVE_EDITS:
        receipts.append(edit.apply(tree))
    return receipts
