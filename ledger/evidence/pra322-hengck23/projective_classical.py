# SPDX-License-Identifier: Apache-2.0
"""Classical projective left-looking extract (PRA-322 / hengck23 edit 004).

For targets in groups >= THRESH (default 5), keep dual numbers in homogeneous
form (N : D : W) with u = N/D, v = W/D^2 over GF(2^24). Jet update becomes
multiplications + a swap (no field inverse) until the target is materialized
when it becomes a head. Early targets (group < THRESH) keep full affine jets;
THRESH=5 leaves exactly 16 full jets, matching hengck23's 289 -> 16.

Scale identity (matches kickmix extract): after J, v' = u + q*v and u' = q*u
(not v' = q*u + q*v).

This module is evidence / a reference for the quantum patch; it is not an
input to the shipped generator.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tasks/dqi/fused/source'))

from exp.confluent_extract.model import (  # noqa: E402
    J,
    constants,
    coords,
    ehead,
    extract,
    f,
    get,
    initial,
    plan,
    put,
)

THRESH = 5


def _mul(x, y):
    return f.emul(x, y)


def _scale(x, s):
    return f.escale(x, s)


def _inv(x):
    return f.einv(x)


def to_affine(N, D, W):
    if D == 0:
        return 0, W
    Di = _inv(D)
    return _mul(N, Di), _mul(W, _mul(Di, Di))


def affine_jet_step(u, v, a, b, c, q):
    u ^= ehead(a, b, c)
    v ^= b
    u, v = J(u, v)
    v = u ^ _scale(v, q)
    u = _scale(u, q)
    return u, v


def proj_step(N, D, W, a, b, c, q):
    N = N ^ _mul(ehead(a, b, c), D)
    W = W ^ _mul(b, _mul(D, D))
    if N == 0:
        N2, D2, W2 = 0, D, W
    else:
        N2, D2, W2 = D, N, W
    # v' = u + q*v ; u' = q*u
    return _scale(N2, q), D2, _mul(N2, D2) ^ _scale(W2, q)


def projective_extract(bank, *, thresh: int = THRESH, h: int | None = None):
    bank = list(bank)
    h = h or len(bank) // 2
    groups = constants(h)[4]
    word_to_gi = {g['word']: i for i, g in enumerate(groups)}
    head_to_gi = {}
    for i, g in enumerate(groups):
        head_to_gi[g['head']] = i
        if g['double']:
            head_to_gi[g['head'] + 1] = i
    late = {g['word'] for g in groups[thresh:]}
    proj = {w: [get(bank, w), 1, get(bank, w + 2)] for w in late}

    def materialize(w):
        u, v = to_affine(*proj.pop(w))
        put(bank, w, u)
        put(bank, w + 2, v)

    for op in plan(h):
        if op['kind'] == 'coordinates':
            g = groups[head_to_gi[op['head']]]
            if g['word'] in proj:
                materialize(g['word'])
            bank[2 * op['head']] ^= f.mul(op['c'], bank[2 * op['head'] + 1])
            continue
        if op['kind'] == 'local':
            i = 2 * op['head']
            j = i + 2
            u = get(bank, j) ^ bank[i + 1]
            aa, bb = coords(f.einv(u), op['c'])
            bank[j:j + 2] = [aa, bb]
            continue
        j = op['target']
        a, b = bank[2 * op['head']:2 * op['head'] + 2]
        q, c = op['q'], op['c']
        if word_to_gi[j] < thresh:
            u, v = affine_jet_step(get(bank, j), get(bank, j + 2), a, b, c, q)
            put(bank, j, u)
            put(bank, j + 2, v)
        else:
            proj[j] = list(proj_step(*proj[j], a, b, c, q))
    for w in list(proj):
        materialize(w)
    return bank


def self_check(repeats: int = 20) -> dict:
    import random
    from exp.confluent_extract.model import instance

    h = 35
    rng = random.Random(20261029)
    ok = 0
    for _ in range(repeats):
        weight = rng.randint(0, 12)
        roots = rng.sample(range(1, 4096), weight)
        weights = [rng.randrange(1, 4096) for _ in roots]
        bank0 = initial(instance(h, roots, weights)['syndrome'], h)
        if projective_extract(bank0) == extract(bank0, h):
            ok += 1
    jets = sum(1 for op in plan(h) if op['kind'] == 'jet')
    full = sum(
        1
        for op in plan(h)
        if op['kind'] == 'jet' and {g['word']: i for i, g in enumerate(constants(h)[4])}[op['target']] < THRESH
    )
    return {'matches': ok, 'repeats': repeats, 'total_jets': jets, 'full_jets_at_thresh': full}


if __name__ == '__main__':
    import json
    print(json.dumps(self_check(), indent=2))
