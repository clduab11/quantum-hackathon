# SPDX-License-Identifier: Apache-2.0
"""Fit weights against fixed, decoded rounded vectors; no surrogate gradient."""
import numpy as np
from scipy.optimize import minimize


def weight_value_grad(flat, shape, v, target, penalty):
    """Full packed Frobenius residual and D(w), with analytic weight gradient."""
    w = flat.reshape(shape)
    a = (w.transpose(0, 2, 1) @ v).reshape(-1, v.shape[-1])
    residual = a.T @ a - target
    error = np.linalg.norm(residual)
    ga = (2 * (a @ residual) / max(error, 1e-30)).reshape(shape[0], shape[2], -1)
    gradient = v @ ga.transpose(0, 2, 1)
    absolute, signed = np.abs(w).sum(axis=1), w.sum(axis=1)
    d = .5 * np.sum(absolute**2 - signed**2)
    gradient += penalty * (np.sign(w)*absolute[:, None, :] - signed[:, None, :])
    return float(error + penalty*d), gradient.ravel()


def refit_quantized(params, target, steps, penalty, quantize, maxcor=20):
    """Round U through the pinned encoder callback, freeze it, and refit W.

    The callback must return normalized decoded vectors at the requested width.
    H2_I is retained for a subsequent offset refinement. No optimizer flag is
    an accuracy verdict: evaluate the final encoded words independently.
    """
    if steps < 1 or maxcor < 1 or not np.isfinite(penalty) or penalty < 0:
        raise ValueError('steps/maxcor must be positive; penalty finite and nonnegative')
    output = {k: np.array(v, copy=True) for k, v in params.items()}
    u = np.asarray(quantize(params['U']), dtype=np.float64)
    if u.shape != params['U'].shape or not np.isfinite(u).all():
        raise ValueError('quantized vectors must be finite and match U shape')
    if not np.allclose(np.linalg.norm(u, axis=-1), 1., rtol=0, atol=1e-12):
        raise ValueError('quantized vectors must be normalized')
    i, j = np.tril_indices(u.shape[-1])
    v = u[:, :, i] * u[:, :, j] * np.where(i == j, 1., np.sqrt(2.))
    w = params['W']
    args = (w.shape, v, target, penalty)
    initial = weight_value_grad(w.ravel(), *args)[0]
    result = minimize(weight_value_grad, w.ravel(), args=args, jac=True,
                      method='L-BFGS-B', options=dict(maxiter=steps, maxcor=maxcor,
                      maxls=30, ftol=1e-12, gtol=1e-8))
    output.update(U=u.copy(), W=result.x.reshape(w.shape))
    return output, dict(iterations=int(result.nit), evaluations=int(result.nfev),
                        converged=bool(result.success), message=str(result.message),
                        objective=float(result.fun), initial_objective=initial,
                        maxcor=maxcor, method='fixed-rounded-U weight L-BFGS-B')
