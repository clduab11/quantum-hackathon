# SPDX-License-Identifier: Apache-2.0
"""PRA-246 port of ViberTeam v2 methods; attribution and changes in FIT_V4.md."""
from __future__ import annotations
import math
from typing import Any, Mapping
from dataclasses import replace
import numpy as np
from scipy.optimize import minimize


def evaluate_words(context, data, brot):
    """Call the unchanged competition entry point, not a training surrogate."""
    from dfthcsos.verify import evaluate_words as evaluate
    w, offsets, shift, beta = native_inputs(context, data)
    inputs = replace(context.inputs, params=data, w=w, W=offsets, S=shift, beta_1=beta)
    return evaluate(inputs, data['angle_words'], data['tree_edges'], brot)


def packed_target(context, data):
    from tasks.dfthcsos.factor_math import packed_target as pack
    if context.packed_target is None:
        context.packed_target = pack(context.reference['tei'], native_inputs(context, data)[2])
    return context.packed_target

def copy_data(data: Mapping[str, Any]) -> dict[str, np.ndarray]:
    return {key: np.array(value, copy=True) for key, value in data.items()}


def native_inputs(context: Context, data: Mapping[str, Any]):
    """Use exactly the fixed-shift and float32 symmetrization convention."""
    w = np.asarray(data["W"], dtype=np.float64)
    offset = np.asarray(data["H2_I"], dtype=np.float64) - w.sum(axis=1)
    n = np.shape(data["U"])[-1]
    shift = np.asarray(context.math.symmetric_from_lower(
        context.fixed_shifts["Hsym_lower"], n), dtype=np.float64)
    beta = float(context.fixed_shifts["H1_I"]) - 0.5 * np.trace(shift)
    return w, offset, shift, float(beta)


def encode_vectors(vectors: np.ndarray, tree_edges: np.ndarray, brot: int) -> np.ndarray:
    """Reverse the ordered Givens tree, then round angles to nearest words."""
    if not 1 <= brot <= 30:
        raise ValueError("this numerical encoder supports 1 <= brot <= 30")
    work = np.asarray(vectors, dtype=np.float64).copy()
    work /= np.linalg.norm(work, axis=1, keepdims=True)
    angles = np.empty((len(work), len(tree_edges)), dtype=np.float64)
    for j in reversed(range(len(tree_edges))):
        parent, child = tree_edges[j]
        angles[:, j] = np.arctan2(work[:, child], work[:, parent])
        work[:, parent] = np.hypot(work[:, parent], work[:, child])
        work[:, child] = 0.0
    return np.rint(angles * (2 ** (brot - 1) / np.pi)).astype(np.int64) % (1 << brot)


def decoded_vectors(context: Context, data: Mapping[str, Any], brot: int):
    n = np.shape(data["U"])[-1]
    r, b, _ = np.shape(data["W"])
    vectors = context.math.reconstruct_u_vectors(
        np.asarray(data["angle_words"]) / (1 << (brot - 1)), data["tree_edges"])
    return vectors[:n], vectors[n:].reshape(r, b, n)


def refresh_one_body(context: Context, data: Mapping[str, Any], brot: int):
    """Re-encode the actual h1-prime eigenvectors after modifying factors."""
    result = copy_data(data)
    _, u = decoded_vectors(context, result, brot)
    w, offsets, shift, beta = native_inputs(context, result)
    n = u.shape[-1]
    coefficients = np.einsum("rc,rbc->rb", offsets, w)
    h1 = (context.reference["h1_thc"]
          - 0.5 * context.reference["electrons"] * shift + beta * np.eye(n)
          - np.einsum("rb,rbp,rbq->pq", coefficients, u, u, optimize=True))
    _, vectors = np.linalg.eigh(h1)
    result["angle_words"][:n] = encode_vectors(vectors.T, result["tree_edges"], brot)
    return result


def optimize_effective_norm(context: Context, data: Mapping[str, Any], brot: int,
                            *, maxiter: int = 240, gap_margin: float = 0.001):
    """Optimize the actual lambda_eff, including the LCU one-norm derivative.

    Minimizing the SOS gap alone ignores the way identity offsets change
    Lambda. This routine trades both physical quantities using their exact
    eigenvalue derivatives. A penalty enforces a positive acceptance margin;
    reported quantities are recomputed from the real parameters, never clipped.
    """
    result = copy_data(data)
    _, u = decoded_vectors(context, result, brot)
    w, original, shift, beta = native_inputs(context, result)
    r, _, c = w.shape
    n = u.shape[-1]
    constant = (context.reference["h1_thc"]
                - 0.5 * context.reference["electrons"] * shift + beta * np.eye(n))
    energy = context.energy_upper - context.reference["ecore"] + context.reference["electrons"] * beta
    sum_w = w.sum(axis=1)
    l1_w = np.abs(w).sum(axis=1)
    floor = 3.914898 + gap_margin
    def quantities(flat):
        offsets = flat.reshape(r, c)
        combined = np.einsum("rc,rbc->rb", offsets, w)
        h1 = constant - np.einsum("rb,rbp,rbq->pq", combined, u, u, optimize=True)
        values, vectors = np.linalg.eigh(h1)
        sign_h1 = (vectors * np.sign(values)) @ vectors.T
        contractions = np.einsum("rbp,pq,rbq->rb", u, sign_h1, u, optimize=True)
        gap = float(energy + np.abs(values).sum() - values.sum() + 0.5 * np.sum(offsets ** 2))
        w_b = offsets + sum_w
        lam = float(np.abs(values).sum() + 0.25 * np.sum((l1_w + np.abs(w_b)) ** 2))
        grad_gap = offsets + np.einsum("rb,rbc->rc", 1.0 - contractions, w)
        grad_lam = (-np.einsum("rb,rbc->rc", contractions, w)
                    + 0.5 * (l1_w + np.abs(w_b)) * np.sign(w_b))
        return gap, lam, grad_gap, grad_lam
    def objective(flat):
        gap, lam, grad_gap, grad_lam = quantities(flat)
        radicand = gap * (2.0 * lam - gap)
        if radicand <= 0:
            return 1e12 + abs(radicand), np.zeros_like(flat)
        loss = 0.5 * math.log(radicand)
        gradient = ((lam - gap) * grad_gap + gap * grad_lam) / radicand
        if gap < floor:
            loss += 1e5 * (floor - gap) ** 2
            gradient -= 2e5 * (floor - gap) * grad_gap
        if lam < 49.001:
            loss += 1e5 * (49.001 - lam) ** 2
            gradient -= 2e5 * (49.001 - lam) * grad_lam
        return loss, gradient.ravel()
    gap0, lam0, _, _ = quantities(original.ravel())
    optimized = minimize(objective, original.ravel(), jac=True, method="L-BFGS-B",
                         options={"maxiter": maxiter, "maxcor": 12,
                                  "ftol": 1e-13, "gtol": 1e-8, "maxls": 40})
    offsets = optimized.x.reshape(r, c)
    gap1, lam1, _, _ = quantities(offsets.ravel())
    before = math.sqrt(gap0 * (2.0 * lam0 - gap0))
    after = math.sqrt(gap1 * (2.0 * lam1 - gap1))
    accepted = gap1 > 3.914898 and lam1 > 49.0 and after < before
    if accepted:
        result["H2_I"] = offsets + sum_w
        result = refresh_one_body(context, result, brot)
    return result, {"lambda_eff_before": before, "lambda_eff_after": after,
                    "gap_before": gap0, "gap_after": gap1,
                    "Lambda_before": lam0, "Lambda_after": lam1,
                    "iterations": int(optimized.nit), "success": bool(optimized.success),
                    "accepted": bool(accepted)}
