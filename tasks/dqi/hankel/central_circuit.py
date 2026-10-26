# SPDX-License-Identifier: Apache-2.0
# Port of SomeJoint v7; see PROVENANCE.md and SOURCE_MAP.json.
# Praxen: package imports; production functions only; no notebook runtime.
"P1 central Jacobi repair with a pivot-free tridiagonal middle map.\n\nReuses the read/verified border arithmetic and first-gap pointer. The middle\nmap is the independently derived Hessenberg factorization of a tridiagonal\nmatrix. It uses the field sub-agent's fully read 11-scratch recursive LDU\nscaler (`../field/recursive_ldu.py`, with attribution and native records).\n\nThis is a candidate module, not an official-PASS assertion. The first-gap\nand higher-gap approximations are retained; terminal-kernel behavior is\nchecked at the final Forney values, not claimed as an exact singular solve."
from __future__ import annotations

from .border_circuit import Scaling, divide_locator, product, GF, km
from .retry_circuit import FirstGap, controlled_scale, rotate
from .recursive_ldu import scale_words as low_space_scale


class CentralGap(FirstGap):
    def __init__(self, b, degree, vectors, counts):
        super().__init__(b, degree, counts)
        self.vectors = vectors
        self.constants = [None]*degree

    def prefix_xor(self, code, flag):
        # 1 <= first-gap code <= code, excluding the empty pointer value 0.
        self.b.flip_if_less_than(self.pointer, code+1, target=flag)
        self.b.flip_if_equal(self.pointer, 0, target=flag)

    def prefix(self, code):
        flag = self.b.alloc_qubits(1)[0]
        self.prefix_xor(code, flag)
        return flag

    def unprefix(self, code, flag):
        self.prefix_xor(code, flag)
        self.b.free(flag)

    def masked_products(self, source, targets, flag):
        b = self.b
        mask = b.alloc_qubits(12)
        b.init_and(flag, source, mask)
        self.counts["central_mask_ands"] += 12
        for rhs, target in targets:
            b.ixor_gf2_mul(mask, rhs, target=target, field=GF)
            self.counts["central_products"] += 1
        b.del_and(flag, source, mask)
        b.free(mask)

    def middle(self, *, reverse=False):
        """Controlled leading-prefix T, with determinant 0 extended to 1."""
        b, n = self.b, self.degree
        assert all(word is not None for word in self.constants)

        def lower_band(inv):
            indices = range(1, n) if inv else reversed(range(1, n))
            for i in indices:
                code = n-i
                flag = self.prefix(code)
                for v in self.vectors:
                    tmp = b.alloc_qubits(12)
                    b.ixor_gf2_mul(self.constants[i], v[i-1], target=tmp, field=GF)
                    if i >= 2:
                        b.cx(v[i-2], tmp)
                    b.ccx(flag, tmp, v[i])
                    if i >= 2:
                        b.cx(v[i-2], tmp)
                    b.del_gf2_mul(self.constants[i], v[i-1], target=tmp, field=GF)
                    b.free(tmp)
                    self.counts["central_products"] += 1
                    self.counts["central_controlled_xor_bits"] += 12
                self.unprefix(code, flag)

        if reverse:
            lower_band(True)
        previous = b.alloc_qubits(12)
        b.x(previous[0])
        current = self.constants[0]  # Borrow b0; every later coefficient is read-only.

        def carry_step(i, inv):
            code = n-i
            flag = self.prefix(code)
            if inv:
                b.cswap(flag, previous, current)
            self.masked_products(current, [(self.constants[i], previous)], flag)
            if not inv:
                b.cswap(flag, previous, current)
            self.counts["central_controlled_word_swaps"] += 1
            self.unprefix(code, flag)

        def upper_step(i, inv):
            code = n-i-1
            flag = self.prefix(code)
            if not inv:
                for v in self.vectors:
                    b.cswap(flag, v[i], v[i+1])
            self.masked_products(current, [(v[i+1], v[i]) for v in self.vectors], flag)
            if inv:
                for v in self.vectors:
                    b.cswap(flag, v[i], v[i+1])
            self.counts["central_controlled_word_swaps"] += len(self.vectors)
            self.unprefix(code, flag)

        for i in range(n):
            if i:
                carry_step(i, False)
            if not reverse and i+1 < n:
                upper_step(i, False)

        empty = b.alloc_qubits(1)[0]
        b.flip_if_equal(self.pointer, 0, target=empty)
        b.cswap(empty, previous, current)  # No repair => scalar exactly 1.
        b.flip_if_equal(self.pointer, 0, target=empty)
        b.free(empty)
        self.counts["central_controlled_word_swaps"] += 1

        def route(inv):
            indices = reversed(range(1, n)) if inv else range(1, n)
            for i in indices:
                code = n-i
                flag = self.read(code)
                for v in self.vectors:
                    b.cswap(flag, v[0], v[i])
                self.counts["central_controlled_word_swaps"] += len(self.vectors)
                self.unread(code, flag)

        route(False)
        low_space_scale(b, current, [v[0] for v in self.vectors], divide=reverse)
        self.counts["central_ldu_scalers"] += 1
        route(True)
        empty = b.alloc_qubits(1)[0]
        b.flip_if_equal(self.pointer, 0, target=empty)
        b.cswap(empty, previous, current)
        b.flip_if_equal(self.pointer, 0, target=empty)
        b.free(empty)
        self.counts["central_controlled_word_swaps"] += 1

        for i in reversed(range(n)):
            if reverse and i+1 < n:
                upper_step(i, True)
            if i:
                carry_step(i, True)
        b.x(previous[0])
        b.free(previous)
        if not reverse:
            lower_band(False)

    def base(self, b, p, d, vectors, counts, *, reverse):
        assert len(p) == 2 and len(d) == 1
        self.constants[0] = p[0]

        def enter(inv):
            scale = Scaling(b, d[0], counts)
            if not inv:
                scale.apply(p[0], divide=True)
                scale.apply(p[1], divide=True)
            for v in vectors:
                scale.apply(v[0], divide=not inv)
            if inv:
                scale.apply(p[1], divide=False)
                scale.apply(p[0], divide=False)
            scale.close()

        def first(inv):
            scale = Scaling(b, p[1], counts)
            for v in vectors:
                scale.apply(v[0], divide=not inv)
            scale.close()

        def middle(inv):
            self.middle(reverse=inv)

        def extra(inv):
            flag = self.prefix(self.degree)
            scale = Scaling(b, p[1], counts)
            for v in vectors:
                controlled_scale(scale, v[0], flag, divide=not inv)
            scale.close()
            self.unprefix(self.degree, flag)

        def leave(inv):
            scale = Scaling(b, d[0], counts)
            if inv:
                scale.apply(p[0], divide=True)
                scale.apply(p[1], divide=True)
            for v in vectors:
                scale.apply(v[0], divide=not inv)
            if not inv:
                scale.apply(p[1], divide=False)
                scale.apply(p[0], divide=False)
            scale.close()

        actions = [enter, first, middle, extra, leave]
        for action in reversed(actions) if reverse else actions:
            action(reverse)

    def run(self, b, p, d, vectors, counts, *, reverse=False, monic=False):
        n = len(d)
        if n == 1:
            assert not monic
            return self.base(b, p, d, vectors, counts, reverse=reverse)
        code = self.degree-n+1
        self.constants[n-1] = p[n-1]
        self.push(d, code)
        flag = self.read(code)
        rotate(b, d, flag)
        counts["controlled_word_swaps"] += n-1
        self.unread(code, flag)

        def low_update():
            for v in vectors:
                for i in range(n-1):
                    product(b, d[i], v[n-1], v[i], counts)

        def high_update():
            for v in vectors:
                for i in range(n-1):
                    product(b, d[i], v[i], v[n-1], counts)

        def enter(inv):
            scale = Scaling(b, d[-1], counts)
            if not inv:
                for v in vectors:
                    scale.apply(v[-1], divide=True)
                low_update()
                divide_locator(b, p, d, scale, counts, monic=monic)
                if monic:
                    for v in vectors:
                        scale.apply(v[-1], divide=False)
            else:
                if monic:
                    for v in vectors:
                        scale.apply(v[-1], divide=True)
                divide_locator(b, p, d, scale, counts, reverse=True, monic=monic)
                low_update()
                for v in vectors:
                    scale.apply(v[-1], divide=False)
            scale.close()

        def first(inv):
            if monic:
                return
            scale = Scaling(b, p[n], counts)
            for v in vectors:
                scale.apply(v[-1], divide=not inv)
            scale.close()

        def descend(inv):
            self.run(b, d, p[:n-1], [v[:n-1] for v in vectors], counts, reverse=inv)

        def extra(inv):
            if monic:
                return
            flag = self.prefix(code)
            scale = Scaling(b, p[n], counts)
            for v in vectors:
                controlled_scale(scale, v[-1], flag, divide=not inv)
            scale.close()
            self.unprefix(code, flag)

        def leave(inv):
            flag = self.prefix(code) if monic else None
            scale = Scaling(b, d[-1], counts)
            if not inv:
                if monic:
                    for v in vectors:
                        controlled_scale(scale, v[-1], flag, divide=False)
                high_update()
                for v in vectors:
                    scale.apply(v[-1], divide=True)
                divide_locator(b, p, d, scale, counts, reverse=True, monic=monic)
            else:
                divide_locator(b, p, d, scale, counts, monic=monic)
                for v in vectors:
                    scale.apply(v[-1], divide=False)
                high_update()
                if monic:
                    for v in vectors:
                        controlled_scale(scale, v[-1], flag, divide=True)
            scale.close()
            if monic:
                self.unprefix(code, flag)

        actions = [enter, first, descend, extra, leave]
        for action in reversed(actions) if reverse else actions:
            action(reverse)
        flag = self.read(code)
        rotate(b, d, flag, reverse=True)
        counts["controlled_word_swaps"] += n-1
        self.unread(code, flag)
        self.pop(d, code)


def central_border(b, p, d, vectors, counts, *, reverse=False, monic=False):
    assert len(d) >= 2
    repair = CentralGap(b, len(d), vectors, counts)
    repair.run(b, p, d, vectors, counts, reverse=reverse, monic=monic)
    repair.close()
