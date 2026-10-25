# SPDX-License-Identifier: Apache-2.0
"""Refine identity offsets at fixed U/W and fixed symmetry shift on the CPU."""
import numpy as np
from scipy.optimize import minimize


def offset_value_grad(flat, x, w, hbase, energy_constant):
    """Smooth-region gradient of lambda_eff plus strict-floor soft penalties."""
    offsets = flat.reshape(w.shape[0], w.shape[2])
    h = hbase - np.einsum('rc,rcpq->pq', offsets, x)
    vals, vecs = np.linalg.eigh(h)
    sign_h = (vecs * np.sign(vals)) @ vecs.T
    identity = np.eye(len(h))
    l1 = np.abs(vals).sum()
    h2i = offsets + w.sum(axis=1)
    sums = np.abs(w).sum(axis=1) + np.abs(h2i)
    lam = l1 + .25 * np.sum(sums**2)
    gap = energy_constant + l1 - np.trace(h) + .5 * np.sum(offsets**2)
    dl = -np.einsum('pq,rcpq->rc', sign_h, x) + .5 * sums * np.sign(h2i)
    dg = -np.einsum('pq,rcpq->rc', sign_h - identity, x) + offsets
    square = gap * (2 * lam - gap)
    # Extend outside the physical domain with positive floor/domain penalties.
    value = np.sqrt(max(square, 1e-20))
    grad = (gap * dl + (lam - gap) * dg) / value if square > 0 else np.zeros_like(dl)
    for violation, derivative in ((49.0001-lam, -dl),
                                 (3.915-gap, -dg), (gap-2*lam, dg-2*dl)):
        if violation > 0:
            value += 1e4 * violation**2
            grad += 2e4 * violation * derivative
    return float(value), grad.ravel()


def refine_offsets(params, inputs, steps):
    w = params['W']
    u = params['U'] / np.linalg.norm(params['U'], axis=2, keepdims=True)
    x = np.einsum('rbp,rbq,rbc->rcpq', u, u, w, optimize=True)
    hbase = (inputs.ref['h1_thc'] - .5 * inputs.ref['electrons'] * inputs.S
             + inputs.beta_1 * np.eye(u.shape[-1]))
    constant = inputs.energy_upper - inputs.ref['ecore'] + inputs.ref['electrons'] * inputs.beta_1
    start = (params['H2_I'] - w.sum(axis=1)).ravel()
    result = minimize(offset_value_grad, start, args=(x, w, hbase, constant),
                      jac=True, method='L-BFGS-B',
                      options=dict(maxiter=steps, maxls=30, ftol=1e-12, gtol=1e-8, maxcor=5))
    p = {k: np.array(v, copy=True) for k, v in params.items()}
    p['H2_I'] = result.x.reshape(start.size // w.shape[2], w.shape[2]) + w.sum(axis=1)
    return p, dict(iterations=int(result.nit), converged=bool(result.success),
                   message=str(result.message), objective=float(result.fun))
