# SPDX-License-Identifier: Apache-2.0
# Port of SomeJoint v7; see PROVENANCE.md and SOURCE_MAP.json.
# Praxen: package imports; production functions only; no notebook runtime.
"P1 reversible ordinary-border microcircuit; not a full DQI decoder.\n\nThe rank-one Bezoutian schedule is independently implemented here. Arithmetic\ncomes through the parent's reviewed Apache-2.0 paired-v6 adapter; see its\nNOTICE. Low-space inverse implementation is ViberTeam's norm-recycling/HMR\nmethod, read in full before reuse. Every pivot uses a reversible zero-to-one\nextension. This does not claim interior degree-gap correctness."
from __future__ import annotations

from ..jfraction.common import km
from ..jfraction.smallspace_inverse import clear_inverse_hmr
# Upstream runtime installs this substitution before importing border_circuit.
from ..jfraction.norm_recycle_inverse import init_norm_recycle_inverse
GF = km.GF2Field(12)


class Scaling:
    """Low-space shared pivot inverse; one field product per scaled word."""
    def __init__(self, b, pivot, counts):
        self.b, self.pivot, self.counts = b, pivot, counts
        self.zero = b.alloc_qubits(1)[0]
        b.flip_if_equal(pivot, 0, target=self.zero)
        b.cx(self.zero, pivot[0])
        self.inverse = init_norm_recycle_inverse(b, pivot, field=GF)
        self.tmp = b.alloc_qubits(12)
        counts["inverse_groups"] += 1

    def apply(self, word, divide):
        b = self.b
        factor, undo = ((self.inverse, self.pivot) if divide
                        else (self.pivot, self.inverse))
        b.ixor_gf2_mul(word, factor, target=self.tmp, field=GF)
        b.swap(word, self.tmp)
        b.del_gf2_mul(word, undo, target=self.tmp, field=GF)
        self.counts["scales"] += 1

    def close(self):
        b = self.b
        b.free(self.tmp)
        clear_inverse_hmr(b, self.pivot, self.inverse, field=GF)
        b.free(self.inverse)
        b.cx(self.zero, self.pivot[0])
        b.flip_if_equal(self.pivot, 0, target=self.zero)
        b.free(self.zero)


def product(b, lhs, rhs, target, counts):
    b.ixor_gf2_mul(lhs, rhs, target=target, field=GF)
    counts["products"] += 1


def divide_locator(b, p, d, scale, counts, *, reverse=False, monic=False):
    """P -> [r_low,q0,q1], or [r_low,q0] if its leading 1 is implicit."""
    n = len(d)
    assert len(p) == n + (0 if monic else 1)
    q1 = scale.inverse if monic else p[n]

    def high_scale():
        if not monic:
            scale.apply(p[n], divide=not reverse)

    def shifted_update():
        for i in range(1, n):
            product(b, q1, d[i-1], p[i], counts)

    def constant_scale():
        scale.apply(p[n-1], divide=not reverse)

    def constant_update():
        for i in range(n-1):
            product(b, p[n-1], d[i], p[i], counts)

    actions = [high_scale, shifted_update, constant_scale, constant_update]
    for action in reversed(actions) if reverse else actions:
        action()


def apply_border(b, p, d, vectors, counts, *, reverse=False, monic=False, recurse=None):
    """Apply inverse Bezoutian on fixed-size ordinary/terminal-zero chart."""
    n = len(d)
    assert len(p) == n + (0 if monic else 1)
    assert all(len(v) == n for v in vectors)
    if n == 1:
        # Two serial scalar groups avoid a held 12-bit product pivot.
        pivots = [d[0]] if monic else [p[1], d[0]]
        for pivot in reversed(pivots) if reverse else pivots:
            scale = Scaling(b, pivot, counts)
            for v in vectors:
                scale.apply(v[0], divide=not reverse)
            scale.close()
        return

    def low_update():
        for v in vectors:
            for i in range(n-1):
                product(b, d[i], v[n-1], v[i], counts)

    def high_update():
        for v in vectors:
            for i in range(n-1):
                product(b, d[i], v[i], v[n-1], counts)

    def enter(inv):
        scale = Scaling(b, d[n-1], counts)
        if not inv:
            for v in vectors:
                scale.apply(v[n-1], divide=True)
            low_update()
            divide_locator(b, p, d, scale, counts, monic=monic)
            if monic:
                for v in vectors:
                    scale.apply(v[n-1], divide=False)
        else:
            if monic:
                for v in vectors:
                    scale.apply(v[n-1], divide=True)
            divide_locator(b, p, d, scale, counts, reverse=True, monic=monic)
            low_update()
            for v in vectors:
                scale.apply(v[n-1], divide=False)
        scale.close()

    def quotient_scale(inv):
        if monic:
            return
        scale = Scaling(b, p[n], counts)
        for v in vectors:
            scale.apply(v[n-1], divide=not inv)
        scale.close()

    def descend(inv):
        child = apply_border if recurse is None else recurse
        child(b, d, p[:n-1], [v[:n-1] for v in vectors], counts, reverse=inv)

    def leave(inv):
        scale = Scaling(b, d[n-1], counts)
        if not inv:
            high_update()
            for v in vectors:
                scale.apply(v[n-1], divide=True)
            divide_locator(b, p, d, scale, counts, reverse=True, monic=monic)
        else:
            divide_locator(b, p, d, scale, counts, monic=monic)
            for v in vectors:
                scale.apply(v[n-1], divide=False)
            high_update()
        scale.close()

    actions = [enter, quotient_scale, descend, leave]
    for action in reversed(actions) if reverse else actions:
        action(reverse)
