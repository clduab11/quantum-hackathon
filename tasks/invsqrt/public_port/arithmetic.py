# SPDX-License-Identifier: Apache-2.0
"""Port of Dmitrii Gluzdov's Apache-2.0 notebook v7, scriptVersionId 361726742.

Source SHA-256 d689cc89f41a6c9130e9f4c3a6b08dfd5d758fcbbb79f527d55cbd3b48e15280.
https://www.kaggle.com/code/dmitriigluzdov/quantum-circuit-compilation-from-source?scriptVersionId=361726742
Credits: Sumit Chongder (centered polynomial), Rudra Bhaskar (split),
Gu/Kemeny/Yelin/Lukin (deferred repairs), Zongao Bian (virtual low bit),
and the authors named in tasks/invsqrt/PROVENANCE.md.
Local changes: package imports; reuse existing arithmetic helpers; remove
notebook setup, fitting drivers, saved-data replay and verifier calls.
"""
# Parent code cell 23.
import numpy as np
from tasks.invsqrt import signed_digit as H


def prepare(cfg, tabs):
    d = np.arange(1 << H.DB, dtype=np.int64)
    Rmax = 0
    spread = 0
    minimum = {}
    maxima = {}
    for key, (k2, k1, k0) in tabs.items():
        r, _ = H.pipeline(cfg, k2, k1, d)
        minimum[key] = int(r.min())
        maxima[key] = int(r.max())
        Rmax = max(Rmax, int(r.max()), k1)
        spread = max(spread, int(r.max() - r.min()))
    for block in range(1, Rmax.bit_length()):
        bases = {k: v >> block for k, v in minimum.items()}
        if all((0 <= tabs[k][1] - (v << block) < 1 << block + 1 and maxima[k] - (v << block) < 1 << block + 1 for k, v in bases.items())):
            break
    return {'block': block, 'rw': block + 1, 'cw': Rmax.bit_length() - block, 'coarse': bases, 'residual': {k: tabs[k][1] - (v << block) for k, v in bases.items()}}

def shift(b, flags, word, L, inverse, prune=True):
    stages = [(1, 1), (2, 2), (3, 4), (4, 8)]
    occ = []
    n = L
    for k, d in stages:
        occ.append(min(n, L + 2) if prune and k == 4 else n)
        n = min(n + d, len(word))
    seq = list(enumerate(stages))
    seq = seq[::-1] if inverse else seq
    for j, (k, d) in seq:
        indices = range(occ[j]) if inverse else reversed(range(occ[j]))
        for i in indices:
            if i + d < len(word):
                zero_boundary = i + d >= L + sum((amount for _, amount in stages[:j]))
                if zero_boundary:
                    if inverse:
                        b.cx(word[i + d], word[i])
                        b.del_and(flags[k], word[i], word[i + d])
                    else:
                        b.init_and(flags[k], word[i], word[i + d])
                        b.cx(word[i + d], word[i])
                else:
                    b.cswap(flags[k], word[i], word[i + d])
