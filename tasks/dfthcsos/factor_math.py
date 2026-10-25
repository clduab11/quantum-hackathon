# SPDX-License-Identifier: Apache-2.0
"""CPU DF-THC structure refit; method provenance is in FACTOR_PIPELINE.md."""
import numpy as np
from tasks.dfthcsos.factor_optimizers import optimize


def packed_target(tei, shift):
    """Fixed-shift target in an orthonormal symmetric-pair basis."""
    i, j = np.tril_indices(len(shift))
    scale = np.where(i == j, 1., np.sqrt(2.))
    target = tei[i[:, None], j[:, None], i[None, :], j[None, :]].copy()
    target += .5 * (shift[i, j, None] * (i == j)[None, :]
                    + (i == j)[:, None] * shift[i, j][None, :])
    return target * scale[:, None] * scale[None, :]


def structure_value_grad(x, ushape, wshape, target, penalty):
    """Full Frobenius residual plus D(w); analytic gradient through row norms."""
    size = int(np.prod(ushape))
    raw, w = x[:size].reshape(ushape), x[size:].reshape(wshape)
    norms = np.linalg.norm(raw, axis=2, keepdims=True)
    if np.any(norms == 0):
        raise ValueError('zero vector in refit; choose a smaller optimizer step')
    u = raw / norms
    i, j = np.tril_indices(ushape[-1])
    scale = np.where(i == j, 1., np.sqrt(2.))
    v = u[:, :, i] * u[:, :, j] * scale
    a = w.transpose(0, 2, 1) @ v
    flat = a.reshape(-1, len(i))
    residual = flat.T @ flat - target
    error = np.linalg.norm(residual)
    ga = (2 * (flat @ residual) / max(error, 1e-30)).reshape(a.shape)
    gw = v @ ga.transpose(0, 2, 1)
    gv = (w @ ga) * scale
    gu = np.zeros_like(u)
    # Pair entries may share a vertex; accumulate instead of fancy-index assignment.
    for p in range(ushape[-1]):
        gu[:, :, p] = (gv[:, :, i == p] * u[:, :, j[i == p]]).sum(axis=2)
        gu[:, :, p] += (gv[:, :, j == p] * u[:, :, i[j == p]]).sum(axis=2)
    gu = (gu - u * (gu * u).sum(axis=2, keepdims=True)) / norms
    absolute, signed = np.abs(w).sum(axis=1), w.sum(axis=1)
    d = .5 * np.sum(absolute**2 - signed**2)
    gw += penalty * (np.sign(w) * absolute[:, None, :] - signed[:, None, :])
    return float(error + penalty * d), np.concatenate([gu.ravel(), gw.ravel()])


def refit(params, target, steps, penalty, maxcor=5, method='lbfgs',
          callback=None, learning_rate=1e-4):
    u, w = params['U'], params['W']
    start = np.concatenate([u.ravel(), w.ravel()])
    def unpack(x):
        output = {k: np.array(v, copy=True) for k, v in params.items()}
        output['U'] = x[:u.size].reshape(u.shape).copy()
        output['W'] = x[u.size:].reshape(w.shape).copy()
        return output
    evaluations = 0
    def fun(x):
        nonlocal evaluations
        evaluations += 1
        return structure_value_grad(x, u.shape, w.shape, target, penalty)
    result = optimize(fun, start, steps, method, maxcor,
                      (lambda x: callback(unpack(x))) if callback else None,
                      learning_rate)
    return unpack(result.x), dict(iterations=int(result.nit), evaluations=evaluations,
                        converged=bool(result.success), message=str(result.message),
                        objective=float(result.fun), optimizer=method, maxcor=maxcor,
                        learning_rate=learning_rate if method == 'adam' else None)


def compress(params, r, b, c):
    """Keep largest groups/bases; truncate each augmented [w; H2_I] SVD."""
    old = params['W'].shape
    if any(new < 1 or new > prev for new, prev in zip((r, b, c), old)):
        raise ValueError('shapes must shrink monotonically and remain positive')
    p = {k: np.array(v, dtype=np.float64, copy=True) for k, v in params.items()}
    u = p['U'] / np.linalg.norm(p['U'], axis=2, keepdims=True)
    x = np.einsum('rbp,rbq,rbc->rcpq', u, u, p['W'], optimize=True)
    keep = np.sort(np.argsort(-np.sum(x*x, axis=(1, 2, 3)), kind='stable')[:r])
    for key in ('U', 'W', 'H2_I'):
        p[key] = p[key][keep]
    if b < old[1]:
        keep_b = np.sort(np.argsort(-np.sum(p['W']**2, axis=2), axis=1,
                                   kind='stable')[:, :b], axis=1)
        for key in ('U', 'W'):
            p[key] = p[key][np.arange(r)[:, None], keep_b]
    if c < old[2]:
        augmented = np.concatenate([p['W'], p['H2_I'][:, None, :]], axis=1)
        left, singular, _ = np.linalg.svd(augmented, full_matrices=False)
        # Fix SVD sign ambiguity to make the output archive reproducible.
        for group in range(r):
            for col in range(c):
                pivot = np.argmax(np.abs(left[group, :, col]))
                if left[group, pivot, col] < 0:
                    left[group, :, col] *= -1
        reduced = left[:, :, :c] * singular[:, None, :c]
        p['W'], p['H2_I'] = reduced[:, :-1], reduced[:, -1]
    return p
