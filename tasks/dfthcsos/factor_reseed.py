# SPDX-License-Identifier: Apache-2.0
"""Regroup Google-derived factors into fewer groups with larger B/C dimensions."""
import numpy as np


def regroup(params, r, b, c):
    """Merge consecutive groups, prune bases by norm, then truncate augmented SVD.

    No external factors or random initialization. An unpruned merge preserves
    the tensor and identity absorption exactly, up to floating-point rounding.
    Pruning is only an initialization; independent verification is mandatory.
    """
    old_r, old_b, old_c = params['W'].shape
    if min(r, b, c) < 1 or r > old_r:
        raise ValueError('regroup dimensions must be positive; R cannot grow')
    groups = np.array_split(np.arange(old_r), r)
    if any(b > len(g)*old_b or c > min(b+1, len(g)*old_c) for g in groups):
        raise ValueError('requested B/C exceed available merged basis or SVD rank')
    output = {k: np.array(v, dtype=np.float64, copy=True) for k, v in params.items()}
    us, ws, offsets = [], [], []
    for group in groups:
        u = params['U'][group].reshape(-1, params['U'].shape[-1])
        weights = params['W'][group]
        keep = np.sort(np.argsort(-np.sum(weights**2, axis=2).ravel(),
                                  kind='stable')[:b])
        merged = np.zeros((b, len(group)*old_c))
        for row, index in enumerate(keep):
            parent, basis = divmod(int(index), old_b)
            merged[row, parent*old_c:(parent+1)*old_c] = weights[parent, basis]
        augmented = np.vstack([merged, params['H2_I'][group].ravel()])
        # Avoid an unnecessary gauge change for exact merges.
        if c == augmented.shape[1]:
            reduced = augmented
        else:
            left, singular, _ = np.linalg.svd(augmented, full_matrices=False)
            left = left[:, :c]
            signs = np.sign(left[np.argmax(np.abs(left), axis=0), np.arange(c)])
            reduced = left * signs * singular[None, :c]
        us.append(u[keep])
        ws.append(reduced[:-1])
        offsets.append(reduced[-1])
    output.update(U=np.stack(us), W=np.stack(ws), H2_I=np.stack(offsets))
    return output
