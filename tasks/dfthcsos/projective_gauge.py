# SPDX-License-Identifier: Apache-2.0
"""Exact integer projective gauge from mrmeows v6; no refit or rounding.

Source and hashes: notices/35-chem-catchup.txt. The gauge changes each
vector only by an overall sign, preserving its outer product.
"""
import numpy as np

def decode_tree(words: np.ndarray, edges: np.ndarray, brot: int) -> np.ndarray:
    n = len(edges) + 1
    result = np.zeros((len(words), n), dtype=np.float64)
    result[:, 0] = 1
    for t, (p, q) in enumerate(edges):
        theta = words[:, t] * (np.pi / (1 << (brot - 1)))
        cp, cq = result[:, p].copy(), result[:, q].copy()
        co, si = np.cos(theta), np.sin(theta)
        result[:, p] = co * cp - si * cq
        result[:, q] = si * cp + co * cq
    return result


def validate_tree(edges: np.ndarray) -> None:
    n = len(edges) + 1
    seen = {0}
    if edges.shape != (n - 1, 2) or not np.issubdtype(edges.dtype, np.integer):
        raise ValueError("tree_edges must be an integer (N-1,2) array")
    for p, q in edges:
        if int(p) not in seen or int(q) in seen or not 0 <= int(q) < n:
            raise ValueError("tree must introduce each new child once in parent-before-child order, rooted at 0")
        seen.add(int(q))


def signed_gauge(words: np.ndarray, edges: np.ndarray, brot: int) -> tuple[np.ndarray, np.ndarray]:
    """Return signed-gauge words and their exact overall vector signs.

    In reverse tree order, preserve a diagonal sign map between original
    and transformed partial vectors.  Negation flips sine; adding pi flips
    both sine and cosine.  The predecessor child's amplitude is zero, so
    its predecessor sign is irrelevant.  At the end only the root sign
    remains.  Thus new_u = root_sign * original_u exactly, over the reals.

    The half-open signed interval includes -pi/2 and excludes +pi/2.
    In particular, this handles quarter-turn and zero-component cases
    with integers; there is no atan2, clipping, or numerical rerounding.
    """
    validate_tree(edges)
    if brot < 2 or words.shape[1] != len(edges):
        raise ValueError("invalid precision or tree/word dimensions")
    modulus = 1 << brot
    if np.any(words < 0) or np.any(words >= modulus):
        raise ValueError("words outside precision range")
    half, quarter = modulus // 2, modulus // 4
    out = np.asarray(words, dtype=np.int64).copy()
    signs = np.ones((len(words), len(edges) + 1), dtype=np.int8)
    for t in reversed(range(len(edges))):
        p, q = edges[t]
        angle = out[:, t]
        angle = np.where(signs[:, p] != signs[:, q], (-angle) % modulus, angle)
        flip_parent = (angle >= quarter) & (angle < 3 * quarter)
        angle = np.where(flip_parent, (angle + half) % modulus, angle)
        out[:, t] = angle
        signs[flip_parent, p] *= -1
        signs[:, q] = 1
    if np.any(((out >> (brot - 1)) ^ (out >> (brot - 2))) & 1):
        raise AssertionError("signed-gauge invariant failed")
    return out, signs[:, 0].copy()
