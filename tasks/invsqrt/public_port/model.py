# SPDX-License-Identifier: Apache-2.0
"""Integer arithmetic for the Gluzdov v7 virtual-low schedule.

Derived from Sumit Chongder's centered signed-digit polynomial as retained
in Gluzdov v7 (scriptVersionId 361726742), cells 22, 29, 34 and 40.
No saved coefficient table, angle file, patch or binary is loaded.
This module deliberately has no kickmix dependency: G2 runs before building.
"""
from dataclasses import dataclass
import math

import numpy as np

MAX_X = 3_133_452


@dataclass(frozen=True)
class Config:
    f2: int = 9
    f1: int = 19
    fyr: int = 26
    gy: int = 2
    drop2: tuple[int, ...] = (5,)

    @property
    def fy(self):
        return self.fyr + self.gy

    @property
    def w2(self):
        return self.f2 - 1

    @property
    def sh2(self):
        return [self.f2 + 22 - i - self.f1 for i in range(14)]

    @property
    def sh1(self):
        return [self.f1 + 22 - i - self.fy for i in range(14)]

    def rrow_list(self):
        return [i for i in reversed(range(14)) if i not in self.drop2 and self.sh2[i] < self.w2]


def rd(value, shift):
    if shift < 0:
        return value << -shift
    return (value >> shift) + (((value >> (shift - 1)) & 1) if shift else 0)


def pipeline(cfg, k2, k1, d):
    """Broadcast over numpy or torch integer arrays, with identical rounding."""
    signs = [2 * ((d >> i) & 1) - 1 for i in range(14)]
    r = d * 0 + k1
    for i in cfg.rrow_list():
        r = r - signs[i] * rd(k2, cfg.sh2[i])
    q = r * 0
    for i in reversed(range(14)):
        q = q + signs[i] * rd(r, cfg.sh1[i])
    return r, q


def interpolation_values(base, step, *, fraction_bits=3, group_bits=3):
    values = tuple(base - sum((2 * ((low >> i) & 1) - 1) * rd(step, fraction_bits-i)
                             for i in range(group_bits)) for low in range(1 << group_bits))
    if min(values) < 0 or max(values) >= 256:
        raise ValueError("curvature outside the eight-bit register")
    return values


def integer_model(xs, cfg, tables):
    xs = np.asarray(xs, dtype=np.int64)
    if np.any((xs < 1) | (xs > MAX_X)):
        raise ValueError("x outside the promised input domain")
    shifts = 22 - np.frexp(xs)[1].astype(np.int64)
    normalized = xs << shifts
    e = shifts & 1
    address = (normalized >> 14) & 127
    rows = np.array([tables[p, a] for p in range(2) for a in range(128)], dtype=np.int64)
    coefficients = rows[e * 128 + address]
    _, q = pipeline(cfg, coefficients[:, 0], coefficients[:, 1], normalized & 16383)
    y = ((coefficients[:, 2] - q) >> cfg.gy) << cfg.gy
    return y << (shifts >> 1)


def certificate(cfg, tables):
    """Check every promised integer against the official integer root formula."""
    worst_ratio, worst_x, minimum, bad, count = 0.0, None, 1 << 64, None, 0
    for start in range(1, MAX_X + 1, 131072):
        xs = np.arange(start, min(start + 131072, MAX_X + 1), dtype=np.int64)
        phase = integer_model(xs, cfg, tables).astype(np.uint64) << np.uint64(64-cfg.fy-10)
        roots = [math.isqrt((1 << 130) // int(x)) for x in xs]
        target = np.array([((r+1) >> 1) & ((1 << 64)-1) for r in roots], dtype=np.uint64)
        tol = np.array([min(r >> 25, 1 << 63) for r in roots], dtype=np.uint64)
        error = np.abs((phase-target).view(np.int64)).astype(np.uint64)
        ratio = error.astype(np.float64) / tol
        i = int(ratio.argmax())
        if ratio[i] > worst_ratio:
            worst_ratio, worst_x = float(ratio[i]), int(xs[i])
        # Python integers avoid overflow at the exact x=1 tolerance boundary.
        margin = min(int(t)-int(v) for t, v in zip(tol, error))
        minimum = min(minimum, margin)
        failures = np.flatnonzero(error > tol)
        if len(failures) and bad is None:
            bad = int(xs[failures[0]])
        count += len(xs)
    return dict(passed=bad is None, tested_inputs=count, worst_ratio=worst_ratio,
                worst_x=worst_x, min_margin_units=minimum, first_bad_x=bad)
