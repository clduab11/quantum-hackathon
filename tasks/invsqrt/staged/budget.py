"""Executable staged-schedule budget, not a circuit or verifier result.

Run ``uv run python -m tasks.invsqrt.staged.budget --require-target``.
Exit 1 means STOP at the design gate. See README.md for evidence and assumptions.
``--fit FILE`` independently recounts the ANF lookups from an existing own fit;
the fit is analysis input only, never a shipping generator input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

BASELINE_COST = 2_076_774.233715282
MARGIN = 78_847_037
FIT_SHA256 = '672e4e010f143c8ff5b40b3e2244a7d3ea0cfb990f42d7a52549cb2543893985'


class WirePool:
    """Lowest-free-id allocator for explicitly declared stage lifetimes.

    Stage boundaries assert that absent registers have been cleaned/HMR'd.
    This models allocation only; it does not prove the quantum transitions.
    """
    def __init__(self):
        self.registers = {}
        self.high_water = 0

    @property
    def live_ids(self):
        return {q for ids in self.registers.values() for q in ids}

    def set_live(self, widths):
        for name in list(self.registers):
            if name not in widths:
                del self.registers[name]
        for name, width in widths.items():
            if width < 0:
                raise ValueError('negative register width')
            if name in self.registers:
                if len(self.registers[name]) != width:
                    raise ValueError('live register resized')
                continue
            used = self.live_ids
            ids = []
            q = 0
            while len(ids) < width:
                if q not in used:
                    ids.append(q)
                q += 1
            self.registers[name] = ids
            self.high_water = max(self.high_water, max(ids, default=-1) + 1)


def cost(qubits, toffoli, *, margin=MARGIN, rotations=44, t_like=1):
    """Same precision/margin pricing as invsqrt.calibrate._estimate."""
    if margin <= 0:
        return dict(qubits=qubits, expected_toffoli=toffoli, rotations=rotations,
                    margin_units=margin, c=math.inf, ratio=0.)
    epsilon = math.pi * (margin / 2**64) / rotations
    rotation_t = 0.56 * math.log2(1 / epsilon) + 5.3
    c = toffoli + (t_like + rotations * rotation_t) / 4
    return dict(qubits=qubits, expected_toffoli=toffoli, rotations=rotations,
                t_like=t_like, margin_units=margin, per_rotation_t=rotation_t,
                c=c, ratio=BASELINE_COST / (qubits * c))


def design_gate(qubits, ratio, *, supported):
    return supported and 0 < qubits <= 63 and math.isfinite(ratio) and ratio >= 18.9


def anf_cost(table):
    """Count DFS ANDs including ancestors of nonzero ANF coefficients."""
    n = len(table).bit_length() - 1
    if len(table) != 1 << n:
        raise ValueError('table length must be a power of two')
    coefficients = list(table)
    for bit in range(n):
        for mask in range(len(table)):
            if mask >> bit & 1:
                coefficients[mask] ^= coefficients[mask ^ (1 << bit)]
    active = set()
    for mask, value in enumerate(coefficients):
        if value:
            while mask.bit_count() > 1:
                active.add(mask)
                mask ^= 1 << (mask.bit_length() - 1)
    return len(active)


def inspect_fit(path):
    """Reproduce split widths and lookup counts without kickmix or CUDA."""
    import numpy as np
    from tasks.invsqrt.public_port.model import Config, pipeline

    data = path.read_bytes()
    fitted = json.loads(data)
    rows = fitted['rows']
    if len(rows) != 256:
        raise ValueError('expected 256 own coefficient rows')
    cfg = Config()
    delta = np.arange(16384, dtype=np.int64)
    extrema = []
    for k2, k1, _ in rows:
        derivative, product = pipeline(cfg, k2, k1, delta)
        extrema.append((int(derivative.min()), int(derivative.max()),
                        int(product.min()), int(product.max())))
    rmax = max(max(z[1], row[1]) for z, row in zip(extrema, rows))
    block = next(b for b in range(1, rmax.bit_length()) if all(
        0 <= row[1] - ((z[0] >> b) << b) < 1 << (b + 1)
        and z[1] - ((z[0] >> b) << b) < 1 << (b + 1)
        for z, row in zip(extrema, rows)))
    low, high, derivative = [], [], []
    for z, (_, k1, k0) in zip(extrema, rows):
        value = k0 % (1 << 20)
        while value - z[3] < 0:
            value += 1 << 20
        if value - z[2] >= 1 << 21 or value & 1:
            raise ValueError('fit does not support this virtual-low layout')
        low.append(value >> 1)
        high.append((k0 - value) >> 20)
        coarse = z[0] >> block
        derivative.append(k1 - (coarse << block) | coarse << (block + 1))
    widths = dict(res=block + 1, coarse=rmax.bit_length() - block,
                  low=max(low).bit_length(), high=max(high).bit_length())
    counts = dict(low=anf_cost(low), high=anf_cost(high), derivative=anf_cost(derivative),
                  high_derivative=anf_cost([h | r << widths['high']
                                           for h, r in zip(high, derivative)]))
    return dict(sha256=hashlib.sha256(data).hexdigest(), widths=widths, lookup_and=counts,
                group8_constant_curvature=all(len({rows[j][0] for j in range(i, i+8)}) == 1
                                             for i in range(0, 256, 8)))


def stages():
    """Two-lookup variant: move index-only high phase before stage A.

    This shares high+derivative lookup. Literal A/B/C order needs three lookups
    and adds another 241 ANDs. Arithmetic and materialized phase kernels here
    remain the current ones; hypothetical tap savings are reported separately.
    """
    pool = WirePool()
    base = dict(x=22, flags=4)
    derivative = dict(res=12, coarse=7)
    rows = []

    def stage(name, registers, toffoli, rotations=0):
        pool.set_live(dict(base, **registers))
        rows.append(dict(name=name, registers=dict(base, **registers),
                         ids={k: list(v) for k, v in pool.registers.items()},
                         live_wires=len(pool.live_ids), allocated_id_high_water=pool.high_water,
                         expected_toffoli=toffoli, rotations=rotations,
                         estimated_global_margin_units=MARGIN))

    stage('normalize', dict(norm_ladder=14), 104)
    stage('high + derivative lookup', dict(derivative, high=8, lookup_ladder=7), 247)
    # High has 18 taps: 15 arbitrary rotations, one T, two Cliffords.
    stage('phase high and HMR', dict(derivative, high=8, phase_extension=10), 66, 15)
    stage('curvature load forward', dict(derivative, c2=8, step=4, lookup_ladder=6), 69)
    stage('inner forward', dict(derivative, c2=8, inner_carry=10), 87)
    stage('coarse carry forward', dict(derivative, coarse_carry=5), 6)
    stage('low lookup', dict(derivative, low=20, lookup_ladder=7), 247)
    stage('outer forward', dict(derivative, low=20, carry=18, virtual_carry=1), 280)
    stage('phase low', dict(derivative, low=20, phase_extension=10), 154, 29)
    stage('outer inverse', dict(derivative, low=20, carry=18, virtual_carry=1), 280)
    # Low is now index-only and can be HMR'd before the inverse inner MAC.
    stage('coarse carry inverse', dict(derivative, coarse_carry=5), 6)
    stage('curvature load inverse', dict(derivative, c2=8, step=4, lookup_ladder=6), 69)
    stage('inner inverse', dict(derivative, c2=8, inner_carry=10), 87)
    stage('merged phase repair', dict(monomials=22, constant=1), 22)
    stage('unnormalize', dict(norm_ladder=14), 89)
    return rows


def report():
    rows = stages()
    q = max(s['allocated_id_high_water'] for s in rows)
    # The raw baseline costs 1566 mean Toffolis. Affine compilation saved 13.
    # Grant that full credit to the new schedule; it has NOT been compiled.
    expected = sum(s['expected_toffoli'] for s in rows) - 13
    target_c = BASELINE_COST / (63 * 18.9)
    optimistic = cost(63, expected - 220 - 138 + 24)
    optimistic['additional_savings_needed'] = optimistic['c'] - target_c
    return dict(
        baseline=cost(84, 1553), staged=cost(q, expected), stages=rows,
        compiler_credit_assumed=13,
        free_phase_taps_bound=cost(q, expected - 220),
        optimistic_q63_bound=optimistic, target_c_at_63=target_c,
        binding_stages=[s['name'] for s in rows if s['live_wires'] == q],
        build_allowed=design_gate(q, cost(q, expected)['ratio'], supported=False),
        assumptions=[
            'All bounds retain 44 rotations, one literal T and baseline calibrated margin.',
            'Margin transfer requires exactly identical phase activations; not verified here.',
            'Optimistic Q63 grants zero-cost phase taps, 12-Toffoli curvature loads twice,',
            'and all area reductions at no extra cost. These are NOT implemented.',
            'Existing 22-Toffoli merged repair is retained; no double-counted repair saving.',
            'No coefficient truncation, dropped rotations, or salt/seed search.',
        ],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-target', action='store_true')
    parser.add_argument('--fit', type=Path)
    args = parser.parse_args()
    result = report()
    if args.fit:
        measured = inspect_fit(args.fit)
        if measured['sha256'] != FIT_SHA256:
            parser.error('fit hash differs from the budget evidence; re-profile before use')
        result['fit_evidence'] = measured
    print(json.dumps(result, indent=2))
    return int(args.require_target and not result['build_allowed'])


if __name__ == '__main__':
    raise SystemExit(main())
