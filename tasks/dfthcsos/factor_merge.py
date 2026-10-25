# SPDX-License-Identifier: Apache-2.0
"""Balanced group merge, simultaneous OMP and PSD refit; see FIT_V3.md."""
import numpy as np
from scipy.linalg import qr, eigh, solve_triangular


def projectors(u):
    u = u / np.linalg.norm(u, axis=-1, keepdims=True)
    i, j = np.tril_indices(u.shape[-1])
    return (u[:, :, i] * u[:, :, j] * np.where(i == j, 1., np.sqrt(2.))).transpose(0, 2, 1)


def select_projectors(p, target, count):
    """Simultaneous orthogonal matching pursuit with deterministic tie breaking."""
    gram, corr = p.T @ p, p.T @ target
    chosen = []
    for _ in range(count):
        score = np.sum(corr**2, axis=1) / np.maximum(np.diag(gram), 1e-16)
        score[chosen] = -np.inf
        k = int(np.argmax(score))
        if gram[k, k] <= 1e-12:
            raise ValueError('projector pool is rank deficient; reduce B')
        chosen.append(k)
        pivot, denominator = gram[:, k].copy(), gram[k, k]
        corr -= np.outer(pivot, corr[k] / denominator)
        gram -= np.outer(pivot, pivot) / denominator
        gram = (gram + gram.T) / 2
    return chosen


def psd_factor(core, count):
    vals, vecs = eigh((core + core.T) / 2, check_finite=False)
    order = np.arange(len(vals)-1, len(vals)-count-1, -1)
    vecs = vecs[:, order]
    signs = np.sign(vecs[np.argmax(np.abs(vecs), axis=0), np.arange(count)])
    return vecs * signs * np.sqrt(np.maximum(vals[order], 1e-14))


def merge_initialize(params, target, shape, sweeps, callback=None):
    """Keep every Google group; replace its merged dictionary using source SOMP."""
    r, b, c = shape
    old_r, old_b, _ = params['W'].shape
    dimension = target.shape[0]
    if not (1 <= r <= old_r and 1 <= c <= b <= min(dimension, old_r//r*old_b) and sweeps >= 0):
        raise ValueError('merge dimensions exceed the available projector or core rank')
    p = projectors(params['U'])
    xs = p @ params['W']
    all_x = xs.transpose(1, 0, 2).reshape(dimension, -1)
    gram = all_x.T @ all_x
    overlap = np.sum(gram.reshape(old_r, -1, old_r, params['W'].shape[2])**2, axis=(1, 3))
    norm = np.sqrt(np.maximum(np.diag(overlap), 1e-30))
    similarity = overlap / np.outer(norm, norm)
    groups = [[k] for k in range(old_r)]
    while len(groups) > r:
        _, _, a, z = min((len(groups[a])+len(groups[z]),
                         -float(np.mean(similarity[np.ix_(groups[a], groups[z])])), a, z)
                        for z in range(len(groups)) for a in range(z))
        groups[a] += groups[z]
        del groups[z]
    us, ws, qs, ts, cores, selections = [], [], [], [], [], []
    for group in groups:
        local_target = np.concatenate(xs[group], axis=1)
        pool = params['U'][group].reshape(-1, params['U'].shape[-1])
        pp = projectors(pool[None])[0]
        chosen = select_projectors(pp, local_target, b)
        q, t = qr(pp[:, chosen], mode='economic', check_finite=False)
        projected = q.T @ local_target
        v = psd_factor(projected @ projected.T, c)
        us.append(pool[chosen]); ws.append(solve_triangular(t, v))
        qs.append(q); ts.append(t); cores.append(v @ v.T); selections.append(chosen)
    result = {k: np.array(v, copy=True) for k, v in params.items()}
    result.update(U=np.asarray(us), W=np.asarray(ws), H2_I=np.zeros((r, c)))
    residual = sum(q @ core @ q.T for q, core in zip(qs, cores)) - target
    report = dict(groups=groups, selected_projectors=selections,
                  initial_error=float(np.linalg.norm(residual)), sweeps=[])
    for sweep in range(sweeps):
        accepted = 0
        for rho, (q, t) in enumerate(zip(qs, ts)):
            v = psd_factor(cores[rho] - q.T @ residual @ q, c)
            core = v @ v.T
            trial = residual + q @ (core - cores[rho]) @ q.T
            if np.sum(trial**2) < np.sum(residual**2):
                residual, cores[rho] = trial, core
                result['W'][rho] = solve_triangular(t, v)
                accepted += 1
        report['sweeps'].append(dict(sweep=sweep+1, accepted=accepted,
                                   error=float(np.linalg.norm(residual))))
        if callback:
            callback(result)
    return result, report
