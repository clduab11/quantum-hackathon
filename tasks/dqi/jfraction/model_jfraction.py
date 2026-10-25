# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Own-ideas model: reversible characteristic-two J-fraction state maps.

No competition source or data is copied. Uses the specified field modulus.
Run through tools/slot; results are model checks, not verifier evidence.
"""
import argparse
import json
import random

MODULUS = 0x1053


def raw_mul(a, b):
    out = 0
    while b:
        if b & 1:
            out ^= a
        b >>= 1
        a <<= 1
        if a & 4096:
            a ^= MODULUS
    return out


EXP = [1]
for _ in range(4094):
    EXP.append(raw_mul(EXP[-1], 2))
assert len(set(EXP)) == 4095
LOG = [0] * 4096
for i, x in enumerate(EXP):
    LOG[x] = i


def mul(a, b):
    return EXP[(LOG[a] + LOG[b]) % 4095] if a and b else 0


def inv(a):
    assert a
    return EXP[-LOG[a] % 4095]


def power(a, n):
    return EXP[LOG[a] * n % 4095] if a else 0


def reciprocal_schedule(a, reverse=False):
    """In-place unit-series inverse by triangular odd-power maps.

    The full sequence is self-inverse as a function; reverse=True reverses
    every elementary XOR, checking the stronger gate-schedule property.
    """
    assert a[0] == 1
    n = len(a)
    ds = []
    d = 2
    exponent = 1
    while exponent < n - 1:
        ds.append(d)
        exponent *= 1 + d
        d *= d
    operations = []
    for d in ds:
        for k in range(n - 1, 0, -1):
            for i in range(1, k // d + 1):
                operations.append((k, i, k - d * i, d))
    for k, i, j, d in reversed(operations) if reverse else operations:
        a[k] ^= mul(power(a[i], d), a[j])
    return sum(j != 0 for _, _, j, _ in operations)


def extract(s):
    """Classical execution of reversible no-zero-pivot extraction map."""
    a = s[:]
    pairs = []
    products = 0
    while a:
        c = a[0]
        if c == 0:
            return pairs, a, products
        ci = inv(c)
        normalized = [1] + [mul(x, ci) for x in a[1:]]
        products += 2 * (len(a) - 1)  # Reversible in-place scaling.
        products += reciprocal_schedule(normalized)
        pairs.append((c, normalized[1]))
        a = normalized[2:]
    return pairs, [], products


def convert(pairs):
    """Bottom-up in-place prepend schedule, modelled using separate lists.

    P holds k cells, Q holds k+1 including implicit Q0=1. Old P cells
    become Q'[2:], old Q[1:] cells become P'[1:], and (c,a) become
    (P'[0],Q'[1]). No additional polynomial array is needed in a circuit.
    """
    p, q = [], [1]
    for c, a in reversed(pairs):
        k = len(p)
        qq = [1, a ^ (q[1] if k else 0)]
        qq += [p[j - 2] ^ (q[j] if j <= k else 0) ^ mul(a, q[j - 1])
               for j in range(2, k + 2)]
        p, q = [c] + [mul(c, x) for x in q[1:]], qq
    return p, q


def unconvert(p, q):
    pairs = []
    while p:
        c = p[0]
        old_q = [1] + [mul(inv(c), x) for x in p[1:]]
        a = q[1] ^ (old_q[1] if len(old_q) > 1 else 0)
        old_p = [q[j] ^ (old_q[j] if j < len(old_q) else 0)
                 ^ mul(a, old_q[j-1]) for j in range(2, len(q))]
        pairs.append((c, a))
        p, q = old_p, old_q
    return pairs


def extract_gaps(s, max_gap=None):
    """Generalized J chart: f=z^r c/(A+z^(r+2) g)."""
    active = s[:]
    layers = []
    while any(active):
        r = next(i for i,x in enumerate(active) if x)
        if max_gap is not None and r > max_gap:
            return layers, active
        if 2*r+2 > len(active):
            return layers, active
        c = active[r]
        unit = [1]+[mul(x,inv(c)) for x in active[r+1:]]
        reciprocal_schedule(unit)
        layers.append((r,c,[1]+unit[1:r+2]))
        active = unit[r+2:]
    return layers,active


def convert_gaps(layers):
    p,q = [],[1]
    for r,c,a in reversed(layers):
        qq = [0]*(len(q)+r+1)
        for i,x in enumerate(a):
            for j,y in enumerate(q):
                qq[i+j] ^= mul(x,y)
        for j,x in enumerate(p):
            qq[j+r+2] ^= x
        p,q = [0]*r+[mul(c,x) for x in q],qq
    return p,q


def unconvert_gaps(p,q):
    layers = []
    while p:
        r = next(i for i,x in enumerate(p) if x)
        c = p[r]
        old_q = [mul(inv(c),x) for x in p[r:]]
        a = [1]
        for j in range(1,r+2):
            value = q[j]
            for i in range(1,min(j,len(old_q)-1)+1):
                value ^= mul(old_q[i],a[j-i])
            a.append(value)
        old_p = []
        for j in range(r+2,len(q)):
            value = q[j]
            for i,x in enumerate(a):
                if 0 <= j-i < len(old_q):
                    value ^= mul(x,old_q[j-i])
            old_p.append(value)
        layers.append((r,c,a))
        p,q = old_p,old_q
    return layers


def series(p, q, n):
    out = [0] * n
    assert q[0] == 1
    for k in range(n):
        out[k] = p[k] if k < len(p) else 0
        for j in range(1, min(k, len(q) - 1) + 1):
            out[k] ^= mul(q[j], out[k-j])
    return out


def syndrome(rng, weight):
    positions = rng.sample(range(4095), weight)
    values = [rng.randrange(1, 4096) for _ in positions]
    s = [0] * 70
    for pos, val in zip(positions, values):
        for i in range(70):
            s[i] ^= mul(val, EXP[((i+1)*pos) % 4095])
    return s




