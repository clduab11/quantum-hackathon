# SPDX-License-Identifier: Apache-2.0
"""Private stage-1 sample seed (research report §6.4).

Fixed per generation so siblings compare on identical inputs. Never rendered
into the LLM prompt — keep this module out of ``prompts/`` and ``DISCOVERY.md``.
"""
from __future__ import annotations

import hashlib
import os

# Opaque constant; not a competition salt and not a verifier nonce.
STAGE1_SEED = int(os.environ.get("SEARCH_STAGE1_SEED", "0xC01DF1A5EED15EED"), 0)


def generation_seed(generation: int) -> int:
    """Deterministic per-generation seed derived from the private base seed.

    Generation 0 is the base seed itself so a smoke run and the first generation
    share one fixed sample without hashing.
    """
    if int(generation) == 0:
        return STAGE1_SEED
    material = f"{STAGE1_SEED}:{int(generation)}".encode("utf-8")
    digest = hashlib.blake2b(material, digest_size=8).digest()
    return int.from_bytes(digest, "big")


def seed_in_text(text: str) -> bool:
    """True when the private base seed (decimal or hex) appears in ``text``."""
    decimal = str(STAGE1_SEED)
    hex_lower = format(STAGE1_SEED, "x")
    hex_upper = format(STAGE1_SEED, "X")
    lowered = text.lower()
    return decimal in text or hex_lower in lowered or f"0x{hex_lower}" in lowered or hex_upper in text
