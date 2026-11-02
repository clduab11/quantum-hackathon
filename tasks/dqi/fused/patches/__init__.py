# SPDX-License-Identifier: Apache-2.0
"""Hengck23 edit layer applied onto a scratch copy of the vendored fused source.

Vendored files under ``fused/source/`` stay byte-identical to SOURCE_MAP.json.
Patches rewrite only the working tree that ``generate_fused`` builds from.
"""
from .apply import ACTIVE_EDITS, apply_patches

__all__ = ['ACTIVE_EDITS', 'apply_patches']
