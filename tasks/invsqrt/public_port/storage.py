"""Exact-domain idle-wire parking, inspired by mrmeows' storage methods.

No saved identities are inputs: sample signatures propose an affine function
plus at most one product, and packed truth vectors prove it on the full domain.
The first strategy requires unchanged recovery operands; the future strategy
replays the idle interval and proves the recovery identity at its endpoint.
A nonlinear or future-recovered wire is erased in X, then its independent
measurement phase is repaired with Z after reconstruction. Immediate affine
parking uses only reversible Clifford gates. The cap is a search target, not
a promised bound: each idle interval is tried once to bound compilation work.
"""
from bisect import bisect_right
from collections import defaultdict
from itertools import combinations

import numpy as np

from tasks.invsqrt import affine


def relation(target, values, full, sample, products=True):
    keys = list(values)
    columns = [full] + [values[q] for q in keys]

    def signature(value):
        result = 0
        for i in sample:
            result = (result << 64) | int(value[i])
        return result

    basis = {}
    signatures = [signature(v) for v in columns]
    for i, vector in enumerate(signatures):
        mask = 1 << i
        while vector:
            pivot = vector.bit_length() - 1
            if pivot not in basis:
                basis[pivot] = vector, mask
                break
            other, coeff = basis[pivot]
            vector ^= other
            mask ^= coeff

    def solve(vector, product):
        mask = 0
        while vector:
            pivot = vector.bit_length() - 1
            if pivot not in basis:
                return None
            other, coeff = basis[pivot]
            vector ^= other
            mask ^= coeff
        exact = np.zeros_like(full)
        if product is not None:
            exact ^= values[product[0]] & values[product[1]]
        for i, column in enumerate(columns):
            if mask >> i & 1:
                exact ^= column
        if np.array_equal(exact, target):
            return [q for i, q in enumerate(keys, 1) if mask >> i & 1], bool(mask & 1), product
        return None

    sig = signature(target)
    answer = solve(sig, None)
    if answer is not None or not products:
        return answer
    for i, j in combinations(range(len(keys)), 2):
        answer = solve(sig ^ (signatures[i+1] & signatures[j+1]), (keys[i], keys[j]))
        if answer is not None:
            return answer
    return None


class StorageCompiler(affine.DomainCompiler):
    def __init__(self, text, cap=68, products=True, future=False):
        super().__init__(text)
        self.cap = cap
        self.products = products
        self.future = future
        self.index = -1
        self.parked = {}
        self.deadlines = {}
        self.events = []
        self.attempted = set()
        self.uses = defaultdict(list)
        self.writes = defaultdict(list)
        self.barriers = []
        for i, line in enumerate(self.lines):
            op = line.split()[0]
            if op in affine._METADATA:
                continue
            qs = [int(q) for q in affine._QUBIT.findall(line)]
            for q in qs:
                self.uses[q].append(i)
            targets = qs if op in ('X', 'R', 'HMR', 'SWAP') else (
                qs[1:] if op == 'CSWAP' else qs[-1:] if op in ('CX', 'CCX') else [])
            for q in targets:
                self.writes[q].append(i)
            if op in ('PUSH_CONDITION', 'POP_CONDITION'):
                self.barriers.append(i)

    def next_at(self, events, q=None):
        values = events if q is None else events[q]
        k = bisect_right(values, self.index)
        return values[k] if k < len(values) else len(self.lines)

    def release(self):
        # Input logical identities remain fixed; physical slots may be reused.
        protected = self.protected
        self.protected = set()
        try:
            super().release()
        finally:
            self.protected = protected

    def restore(self, q):
        terms, constant, product, bit, expected = self.parked.pop(q)
        self.deadlines.pop(q)
        if (set(terms) | set(product or ())) & self.parked.keys():
            raise RuntimeError('Recovery operand is still parked')
        for line in self._clifford(q, terms, constant):
            super().execute(line)
        if product is not None:
            super().execute(f'CCX q{product[0]} q{product[1]} q{q}')
        if bit is not None:
            super().execute(f'Z q{q} if b{bit}')
        if not self.equal(self.val(q), expected):
            raise RuntimeError(f'Parking restoration failed on q{q}')

    def future_values(self, end):
        """Replay a bounded idle interval, without changing the emitted circuit."""
        values = dict(self.values)
        values.update({q: record[-1] for q, record in self.parked.items()})
        def val(q):
            return values.get(q, self.zero)
        for line in self.lines[self.index:end]:
            op = line.split()[0]
            qs = list(map(int, affine._QUBIT.findall(line)))
            if op == 'X':
                for q in qs:
                    values[q] = self.xor(val(q), self.full)
            elif op in ('R', 'HMR'):
                for q in qs:
                    values[q] = self.zero
            elif op == 'CX':
                a, t = qs
                values[t] = self.xor(val(a), val(t))
            elif op == 'CCX':
                a, b, t = qs
                values[t] = self.xor(self.band(val(a), val(b)), val(t))
            elif op == 'SWAP':
                a, b = qs
                values[a], values[b] = val(b), val(a)
            elif op == 'CSWAP':
                c, a, b = qs
                delta = self.band(val(c), self.xor(val(a), val(b)))
                values[a], values[b] = self.xor(val(a), delta), self.xor(val(b), delta)
            elif op not in affine._DIAGONAL | affine._METADATA:
                raise ValueError(f'Cannot preview {op}')
        return values

    def make_room(self, needed):
        if self.depth:
            return
        dependencies = set()
        for terms, _, product, _, _ in self.parked.values():
            dependencies.update(terms)
            dependencies.update(product or ())
        candidates = sorted(set(self.mapping)-needed,
                            key=lambda q: (-self.next_at(self.uses, q), q))
        for q in candidates:
            if len(set(self.mapping) | needed) <= self.cap:
                break
            end = self.next_at(self.uses, q)
            if q in dependencies and (not self.future or any(
                end > self.deadlines[target]
                for target, (terms, _, product, _, _) in self.parked.items()
                if q in terms or q in (product or ())
            )):
                continue
            if end-self.index < 8 or end >= self.next_at(self.barriers) or (q, end) in self.attempted:
                continue
            self.attempted.add((q, end))
            values = {k: v for k, v in self.values.items()
                      if k != q and k not in self.parked and v is not self.zero
                      and self.next_at(self.writes, k) >= end
                      and k not in self.current_writes}
            found = relation(self.val(q), values, self.full, self.sample, self.products)
            deferred = False
            if found is None and self.future and end-self.index <= 400:
                values = {k: v for k, v in self.future_values(end).items()
                          if k != q and k not in self.parked and v is not self.zero}
                found = relation(self.val(q), values, self.full, self.sample, self.products)
                deferred = found is not None
            if found is None:
                continue
            terms, constant, product = found
            expected = self.val(q)
            bit = None
            if product is None and not deferred:
                for line in self._clifford(q, terms, constant):
                    super().execute(line)
            else:
                bit = self.fresh_bit
                self.fresh_bit += 1
                super().execute(f'HMR q{q} b{bit}')
            if self.val(q) is not self.zero:
                raise RuntimeError('Parking failed to erase its target')
            self.parked[q] = terms, constant, product, bit, expected
            self.deadlines[q] = end
            dependencies.update(terms)
            dependencies.update(product or ())
            # Do not subsequently park an operand needed by this restoration.
            self.events.append(dict(line=self.index, until=end, logical=q,
                                    terms=terms, constant=constant, product=product,
                                    deferred=deferred))
            self.rewrites['park_product' if product else 'park_affine'] += 1

    def execute(self, line):
        self.index += 1
        parts = line.split()
        op = parts[0]
        if op in affine._METADATA:
            return super().execute(line)
        needed = set(map(int, affine._QUBIT.findall(line)))
        qs = list(map(int, affine._QUBIT.findall(line)))
        self.current_writes = set(qs if op in ('X', 'R', 'HMR', 'SWAP') else (
            qs[1:] if op == 'CSWAP' else qs[-1:] if op in ('CX', 'CCX') else []))
        for q in sorted(needed & self.parked.keys()):
            self.restore(q)
        if op != 'R' and needed-set(self.mapping):
            self.make_room(needed)
        super().execute(line)

    def compile(self):
        result = super().compile()
        if self.parked:
            raise RuntimeError('Unrestored parked wires')
        # Route the unchanged input state back to the declared physical slots.
        for q in range(22):
            physical = self.mapping[q]
            if physical == q:
                continue
            self.out.append(f'SWAP q{physical} q{q}')
            displaced = next((k for k, v in self.mapping.items() if v == q), None)
            self.mapping[q] = q
            if displaced is not None:
                self.mapping[displaced] = physical
        result.text = '\n'.join(self.out)+'\n'
        return result


def compile_circuit(circuit, cap=68, products=True, future=False):
    compiler = StorageCompiler(str(circuit), cap, products, future)
    result = compiler.compile()
    return result, compiler.events
