# SPDX-License-Identifier: Apache-2.0
"""PRA-246 port of ViberTeam v2 methods; attribution and changes in FIT_V4.md."""
from __future__ import annotations
import numpy as np
COMPACT_KEYS = ("angle_words", "W", "H2_I", "H1_I", "Hsym_lower", "tree_edges")

def canonicalize_words(angle_words, tree_edges, brot=10, *, drift_limit=1e-11):
    """Decode, signed-canonicalize and certify every row up to global sign.

    The certificate concerns already quantized vectors, never an unquantized
    training vector. W/offsets are not fitted or modified by this operation.
    """
    from dfthcsos.scoreinfra.dfthc_math import reconstruct_u_vectors
    words = np.asarray(angle_words)
    edges = np.asarray(tree_edges)
    if brot not in (8, 9, 10, 11, 12) or words.ndim != 2 or not np.issubdtype(words.dtype, np.integer):
        raise ValueError("Expected2D integer words and beta8 or10")
    if np.any(words < 0) or np.any(words >= (1 << brot)):
        raise ValueError("Word outside beta range")
    if edges.shape != (words.shape[1], 2) or not np.issubdtype(edges.dtype, np.integer):
        raise ValueError("tree_edges must have one integer parent/child row per angle")
    n, seen = words.shape[1] + 1, {0}
    for parent, child in edges:
        parent, child = int(parent), int(child)
        if parent not in seen or child in seen or not 0 <= child < n:
            raise ValueError("Gauge requires an ordered rooted Givens tree")
        seen.add(child)
    old = reconstruct_u_vectors(words / (1 << (brot - 1)), edges)
    a, angles = old.copy(), np.empty(words.shape, dtype=np.float64)
    for k, (p, q) in reversed(list(enumerate(edges))):
        norm = np.hypot(a[:, p], a[:, q])
        sign = np.where(np.abs(a[:, p]) < 1e-12,
                        np.where(a[:, q] > 0, -1, 1), np.where(a[:, p] < 0, -1, 1))
        angles[:, k] = np.where(norm < 1e-12, 0,
                                 np.arctan2(a[:, q] * sign, a[:, p] * sign))
        a[:, p] = np.where(norm < 1e-12, 0, norm * sign)
        a[:, q] = 0
    canonical = np.rint(angles * ((1 << (brot - 1)) / np.pi)).astype(np.int64) % (1 << brot)
    if np.any(((canonical >> (brot - 1)) ^ (canonical >> (brot - 2))) & 1):
        raise ArithmeticError("Signed-angle redundant-bit identity failed")
    decoded = reconstruct_u_vectors(canonical / (1 << (brot - 1)), edges)
    row_sign = np.where(np.einsum("ij,ij->i", old, decoded) < 0, -1, 1)
    aligned = decoded * row_sign[:, None]
    drift = float(np.max(np.abs(aligned - old)))
    projector_frob_bound = 2 * np.linalg.norm(aligned - old, axis=1)
    if drift > drift_limit:
        raise ArithmeticError(f"Signed gauge exceeds row component certificate: {drift}")
    report = dict(rows_checked=len(words), angles_per_row=words.shape[1], brot=brot,
                  max_component_drift_up_to_row_sign=drift,
                  max_projector_frobenius_drift_upper_bound=float(projector_frob_bound.max()),
                  redundant_bit_identity=f"bit{brot-1}=bit{brot-2}",
                  certificate="ALL_ROWS_UP_TO_SIGN_WITH_FLOATING_TOLERANCE",
                  physical_accuracy_or_score_claim=False,
                  source="Kozykorpesh V3/run361677445 signed Givens gauge; generalized beta8/beta10")
    return canonical.astype("<u2"), report


def restore_factor(data, brot=10):
    """Regenerate the official U from the signed words; copy all other arrays."""
    from dfthcsos.scoreinfra.dfthc_math import reconstruct_u_vectors
    shape = validate_compact(data, brot)
    result = {key: np.array(data[key], copy=True) for key in COMPACT_KEYS}
    vectors = reconstruct_u_vectors(np.asarray(data["angle_words"]) / (1 << (brot - 1)),
                                    data["tree_edges"])
    result["U"] = vectors[shape["N"]:].reshape(shape["R"], shape["B"], shape["N"])
    return result

def validate_compact(data, brot):
    if brot not in (8, 9, 10, 11, 12):
        raise ValueError("Supported beta values are8 and10")
    missing = set(COMPACT_KEYS) - set(data)
    if missing:
        raise KeyError(f"Missing compact arrays: {sorted(missing)}")
    w, words = np.asarray(data["W"]), np.asarray(data["angle_words"])
    if w.ndim != 3 or min(w.shape) < 1 or not np.all(np.isfinite(w)):
        raise ValueError("W must be finite with positive R/B/C")
    n = words.shape[1] + 1 if words.ndim == 2 else 0
    if words.shape != (n + w.shape[0] * w.shape[1], n - 1):
        raise ValueError("Expected N+R*B angle rows and N-1 columns")
    if not np.issubdtype(words.dtype, np.integer) or np.any(words < 0) or np.any(words >= (1 << brot)):
        raise ValueError("Words must be integers in the requested beta range")
    if np.shape(data["H2_I"]) != (w.shape[0], w.shape[2]):
        raise ValueError("H2_I must have shape(R,C)")
    for key in COMPACT_KEYS[1:]:
        if not np.all(np.isfinite(data[key])):
            raise ValueError(f"Nonfinite compact array {key}")
    if np.shape(data["tree_edges"]) != (n - 1, 2):
        raise ValueError("tree_edges dimensions disagree with words")
    edges = np.asarray(data["tree_edges"])
    if not np.issubdtype(edges.dtype, np.integer):
        raise ValueError("tree_edges must contain integer vertex IDs")
    seen = {0}
    for parent, child in edges:
        parent, child = int(parent), int(child)
        if parent not in seen or child in seen or not 0 <= child < n:
            raise ValueError("Expected an ordered rooted Givens tree")
        seen.add(child)
    if np.shape(data["H1_I"]) not in ((), (1,)):
        raise ValueError("H1_I must be a scalar")
    if np.shape(data["Hsym_lower"]) != (n * (n + 1) // 2,):
        raise ValueError("Hsym_lower must contain the packed lower triangle")
    return dict(N=n, R=int(w.shape[0]), B=int(w.shape[1]), C=int(w.shape[2]),
                addresses=len(words), brot=int(brot))

