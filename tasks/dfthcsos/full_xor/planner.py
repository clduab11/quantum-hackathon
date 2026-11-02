# SPDX-License-Identifier: Apache-2.0
"""Own full-XOR J=5 planner: product basis and cache schedule for any word table.

The committed `plans.json` replays SomeJoint's search; this module is ours. It takes a delta table
(addresses x 5 words, `brot` bits each) and returns the `Plan` and cache schedule that
`emitter.build_staged` turns into an exact XOR oracle. Nothing here builds a circuit.

The model (one Toffoli = one product `(L1+R2)(L2+R1)` with a fanout vector `f`):

* Split the 11 address bits into 4 low and 7 high bits. Every output bit is a Boolean polynomial in the
  address. Its monomials that mix low and high bits form a bilinear tensor `T[l][h][o]`: `l` one of 15 low
  monomials, `h` one of the high monomials, `o` one of F independent output polynomials.
* A product adds `(x1 r1^T + x2 r2^T) (x) f`: a rank-2 matrix times a fanout. Pure-low and pure-high
  monomials are free (they are corrections on cached wires), so only the tensor costs Toffolis.
* So the plan is a set of pairs `(X, f)`, `X` a 2-dim subspace of the low monomials, whose spans
  `X (x) f` contain the span `S` of the tensor's high slices. The 15 low monomials are cut into blocks
  of 3 or 4 that share outputs, and each block is solved on its own. A block is solved by choosing a
  subspace `E = S + W0` for `n0` random first pairs `W0`, spanned by pairs that lie inside it; then the
  pair count is `dim E / 2`.
* The cache schedule (`phasing.py`) puts each pure-low correction in a phase that already holds it.
* The width gate is part of the search. A candidate whose cache would not fit in `max_width` qubits is
  rejected before a schedule or a circuit exists.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from tasks.dfthcsos.full_xor import gf2
from tasks.dfthcsos.full_xor.paired_anf import Plan, Product, anf, batch_deltas, bits, coefficient_polys, output_basis
from tasks.dfthcsos.full_xor.phasing import lower_bound, pure_monomials, search_schedule
from tasks.dfthcsos.full_xor.scheduler import closure, requirements
from tasks.dfthcsos.full_xor.validation import assert_independent

LOW_BITS = 4
LOW = (1 << LOW_BITS) - 1
BATCH = 5
WIDTH_LIMIT = 128


class WidthGateError(RuntimeError):
    """A plan or cache schedule would pass the qubit cap. Raised before anything is emitted."""


@dataclass(frozen=True)
class PlannerConfig:
    sizes: tuple[int, ...] = (3, 4)   # block sizes tried; 3 and 4 beat 2, 5 and 6 on the (8,143,60) tensors
    partitions: int = 1        # block partitions tried per table; the cheapest plan is kept
    restarts: int = 3          # random first phases tried at each first-phase size near the threshold
    max_width: int = WIDTH_LIMIT
    schedule_effort: int = 600  # local-search steps over the order of cache phases, per capacity
    seed: int = 0


@dataclass
class PlanResult:
    plan: Plan
    schedule: dict
    report: dict = field(default_factory=dict)


# --- width gate -----------------------------------------------------------------------------------

def high_cache_size(plan: Plan) -> int:
    return sum(1 for m in plan.cache_masks if m >= 1 << LOW_BITS)


def fixed_width(addresses: int, brot: int, high_cache: int, batch: int = BATCH) -> int:
    """Selection, the five words and the high-monomial cache: everything but the low-monomial slots."""
    return (int(addresses) - 1).bit_length() + batch * brot + high_cache


def peak_width(plan: Plan, capacity: int) -> int:
    """Qubits the emitter will allocate: the same sum as `emitter.build_staged` checks."""
    return fixed_width(plan.addresses, plan.brot, high_cache_size(plan), plan.batch) + int(capacity)


def check_width(plan: Plan, capacity: int, max_width: int = WIDTH_LIMIT) -> int:
    width = peak_width(plan, capacity)
    if width > max_width:
        raise WidthGateError(f'plan needs {width} qubits with {capacity} low slots; the cap is {max_width}')
    return width


def precheck_width(addresses: int, brot: int, max_width: int = WIDTH_LIMIT) -> int:
    """Low slots available at best (at most 11), or WidthGateError when not even one fits.

    This is the most permissive count: it assumes the plan caches no high monomial. It only stops
    hopeless tables and prunes oversized blocks early; the exact gate runs on each assembled plan.
    """
    slots = min(11, max_width - fixed_width(addresses, brot, 0))
    if slots < 1:
        raise WidthGateError(f'selection and words alone need {fixed_width(addresses, brot, 0)} qubits; '
                             f'the cap is {max_width}')
    return slots


# --- the tensor -----------------------------------------------------------------------------------

@dataclass
class Tensor:
    addresses: int
    brot: int
    coeffs: list[int]       # ANF coefficient of every monomial, the packed output bits
    funcs: list[int]        # independent output polynomials (bit m = monomial m)
    fanouts: list[int]      # output-bit mask each independent polynomial drives
    coords: list[int]       # per monomial, which independent polynomials contain it

    @property
    def outputs(self) -> int:
        return len(self.funcs)

    @property
    def high_max(self) -> int:
        return (self.addresses - 1) >> LOW_BITS


def build_tensor(delta, brot: int) -> Tensor:
    addresses, batch = len(delta), len(delta[0])
    if batch != BATCH:
        raise ValueError(f'five words per address required, got {batch}')
    coeffs = anf(delta, brot)
    funcs, fanouts = output_basis(coefficient_polys(coeffs, batch * brot))
    coords = [sum(((poly >> m) & 1) << i for i, poly in enumerate(funcs)) for m in range(addresses)]
    return Tensor(addresses, brot, coeffs, funcs, fanouts, coords)


def block_vectors(tensor: Tensor, monomials: list[int]) -> list[int]:
    """The slices S_h of the tensor on one block, one integer per high monomial h.

    Entry (l, h) with monomial h*16+l at or beyond the address count is a don't-care; it is taken as zero.
    """
    width = tensor.outputs
    out = []
    for h in range(1, tensor.high_max + 1):
        vector = 0
        for a, low in enumerate(monomials):
            m = (h << LOW_BITS) | low
            if m < tensor.addresses:
                vector |= tensor.coords[m] << (width * a)
        out.append(vector)
    return out


# --- one block: pairs whose spans contain the slices ----------------------------------------------

def subspaces(ell: int) -> list[tuple[int, int]]:
    """One (x1, x2) per 2-dim subspace of GF(2)^ell."""
    seen, out = set(), []
    for x1 in range(1, 1 << ell):
        for x2 in range(x1 + 1, 1 << ell):
            key = frozenset((x1, x2, x1 ^ x2))
            if key not in seen:
                seen.add(key)
                out.append((x1, x2))
    return out


class BlockSolver:
    """Pairs (x1, x2, f) over `ell` coordinates and `width` outputs whose spans contain every slice.

    Both searches below fix a subspace E that contains the slices and is spanned by pairs inside it.
    E is described by its annihilator Q (`perp`): x f^T lies in E exactly when x^T Y f = 0 for all Y in Q.
    """

    def __init__(self, slices: list[int], ell: int, width: int):
        self.slices, self.ell, self.width = slices, ell, width
        self.slice_basis = gf2.span_basis(slices)
        self.dim = len(self.slice_basis)
        self.pairs = subspaces(ell) if ell >= 2 else []
        # x -> sum of 1 << (width*a) over a in x, so f * spread[x] puts f in every coordinate of x
        self.spread = {x: sum(1 << (width * a) for a in range(ell) if (x >> a) & 1) for x in range(1, 1 << ell)}
        self.mask = (1 << width) - 1
        self.attempts = 0

    def inside(self, perp: list[int]) -> dict:
        """For every 2-dim subspace X, a basis of {f : X (x) f lies in the annihilator of `perp`}."""
        conditions = {}
        for x in range(1, 1 << self.ell):
            rows = []
            for y in perp:
                row = 0
                for a in range(self.ell):
                    if (x >> a) & 1:
                        row ^= (y >> (self.width * a)) & self.mask
                rows.append(row)
            conditions[x] = rows
        return {pair: gf2.nullspace(conditions[pair[0]] + conditions[pair[1]], self.width) for pair in self.pairs}

    def reach(self, inside: dict, first: list[int]) -> int:
        """Dimension spanned by the first-phase vectors and every pair that lies inside E."""
        reachable = gf2.span_basis(first)
        for pair, fs in inside.items():
            for f in fs:
                gf2.insert(reachable, f * self.spread[pair[0]])
                gf2.insert(reachable, f * self.spread[pair[1]])
        return len(reachable)

    def complete(self, chosen, first, inside, target, rng):
        """Random greedy: add pairs inside E that bring two new dimensions while any does, then one, until E is spanned."""
        spread = self.spread
        have = gf2.span_basis(first)
        chosen = list(chosen)
        order = list(inside)
        for need in (2, 1):
            progress = True
            while len(have) < target and progress:
                progress = False
                rng.shuffle(order)
                for pair in order:
                    fs = inside[pair]
                    if not fs:
                        continue
                    for f in self._candidates(fs, rng):
                        first_new = gf2.reduce(have, f * spread[pair[0]])
                        if first_new:
                            have[first_new.bit_length() - 1] = first_new
                        second_new = gf2.reduce(have, f * spread[pair[1]])
                        if bool(first_new) + bool(second_new) >= need:
                            if second_new:
                                have[second_new.bit_length() - 1] = second_new
                            chosen.append((pair[0], pair[1], f))
                            progress = True
                            break
                        if first_new:
                            del have[first_new.bit_length() - 1]
                    if len(have) >= target:
                        break
        return chosen if len(have) >= target else None

    @staticmethod
    def _candidates(fs, rng, limit=200):
        d = len(fs)
        if d <= 7:
            picks = list(range(1, 1 << d))
            rng.shuffle(picks)
        else:
            picks = [rng.getrandbits(d) or 1 for _ in range(limit)]
        for m in picks:
            f = 0
            for j in range(d):
                if (m >> j) & 1:
                    f ^= fs[j]
            yield f

    def attempt(self, n0: int, rng: random.Random):
        """One random first phase of n0 pairs, then the greedy completion. Returns the pairs or None."""
        self.attempts += 1
        spread = self.spread
        chosen = [(x1, x2, rng.getrandbits(self.width) | 1 << rng.randrange(self.width)) for x1, x2 in
                  (rng.choice(self.pairs) for _ in range(n0))]
        first = [v for x1, x2, f in chosen for v in (f * spread[x1], f * spread[x2])]
        space = gf2.span_basis(first, self.slice_basis)           # E = S + W0
        inside = self.inside(gf2.nullspace(list(space.values()), self.ell * self.width))
        if self.reach(inside, first) < len(space):
            return None
        return self.complete(chosen, first, inside, len(space), rng)

    def solve(self, rng: random.Random, restarts: int):
        """Smallest first phase that completes. Starts low, then retries below the first success."""
        if self.dim == 0:
            return [], 0
        if not self.pairs:
            return self.trivial(), None
        ceiling = (self.ell * self.width) // 2 + 8
        best, best_n0, n0 = None, None, 0
        while n0 <= ceiling and best is None:
            for _ in range(2 if n0 < ceiling else restarts):
                best = self.attempt(n0, rng)
                if best is not None:
                    best_n0 = n0
                    break
            n0 += 1
        if best is None:
            return self.trivial(), None
        while best_n0 > 0:
            better = None
            for _ in range(restarts):
                better = self.attempt(best_n0 - 1, rng)
                if better is not None:
                    break
            if better is None:
                break
            best, best_n0 = better, best_n0 - 1
        return best, best_n0

    def trivial(self):
        """Every unit fanout against the whole block: the always-valid fallback."""
        out = []
        for o in range(self.width):
            for a in range(0, self.ell, 2):
                out.append((1 << a, 1 << (a + 1) if a + 1 < self.ell else 0, 1 << o))
        return out


class Block:
    """A set of low monomials with their slices written in the coordinates of the outputs they touch."""

    def __init__(self, tensor: Tensor, monomials: list[int]):
        self.tensor, self.monomials = tensor, list(monomials)
        rows = []
        for h in range(1, tensor.high_max + 1):
            for low in self.monomials:
                m = (h << LOW_BITS) | low
                if m < tensor.addresses:
                    rows.append(tensor.coords[m])
        self.outputs = list(gf2.span_basis(rows).values())           # basis of the touched outputs
        self.width = len(self.outputs)
        coordinates = gf2.Combinations(self.outputs)
        self.slices = []
        for h in range(1, tensor.high_max + 1):
            vector = 0
            for a, low in enumerate(self.monomials):
                m = (h << LOW_BITS) | low
                if m < tensor.addresses and tensor.coords[m]:
                    vector |= coordinates.solve(tensor.coords[m]) << (self.width * a)
            self.slices.append(vector)

    def solve(self, rng: random.Random, restarts: int):
        if not self.width:
            self.attempts = 0
            return [], 0
        solver = BlockSolver(self.slices, len(self.monomials), self.width)
        pairs, first_phase = solver.solve(rng, restarts)
        self.attempts = solver.attempts
        return self.to_products(solver, pairs), first_phase

    def to_products(self, solver, pairs) -> list[Product]:
        """Solve the slice coefficients r for the chosen pairs and write them as `Product`s."""
        if not pairs:
            return []
        gens = []
        for x1, x2, f in pairs:
            gens.append(f * solver.spread[x1])
            gens.append(f * solver.spread[x2] if x2 else 0)
        combos = gf2.Combinations(gens)
        right = [0] * len(gens)
        for h, vector in enumerate(solver.slices, 1):
            combo = combos.solve(vector)
            if combo is None:
                raise RuntimeError('chosen pairs do not span a slice')
            for k in bits(combo):
                right[k] |= 1 << h
        products = []
        for i, (x1, x2, f) in enumerate(pairs):
            r1, r2 = right[2 * i], right[2 * i + 1]
            if not (r1 or r2):
                continue
            fanout = 0
            for o in bits(f):
                for j in bits(self.outputs[o]):
                    fanout ^= self.tensor.fanouts[j]
            left1 = sum(1 << self.monomials[a] for a in bits(x1))
            left2 = sum(1 << self.monomials[a] for a in bits(x2)) if r2 else 0
            if r1:
                products.append(Product(left1, r1, left2, r2, fanout))
            else:
                products.append(Product(left2, r2, 0, 0, fanout))
        return products


# --- assembly -------------------------------------------------------------------------------------

def product_contribution(products: list[Product], addresses: int) -> dict[int, int]:
    """Coefficient of every monomial below `addresses` that the products produce, mixed or pure."""
    out: dict[int, int] = {}

    def add(m, fanout):
        if m < addresses:
            out[m] = out.get(m, 0) ^ fanout

    for p in products:
        l1, l2 = list(bits(p.left1)), list(bits(p.left2))
        h1, h2 = list(bits(p.right1)), list(bits(p.right2))
        for l in l1:
            for h in h1:
                add(l | (h << LOW_BITS), p.fanout)
        for l in l2:
            for h in h2:
                add(l | (h << LOW_BITS), p.fanout)
        for a in l1:
            for b in l2:
                add(a | b, p.fanout)
        for a in h2:
            for b in h1:
                add((a | b) << LOW_BITS, p.fanout)
    return out


def assemble(tensor: Tensor, products: list[Product]) -> Plan:
    """Plan = products + the pure corrections that make every monomial exact."""
    got = product_contribution(products, tensor.addresses)
    pure = {}
    for m in range(tensor.addresses):
        diff = tensor.coeffs[m] ^ got.get(m, 0)
        if not diff:
            continue
        if (m & LOW) and (m >> LOW_BITS):
            raise RuntimeError(f'mixed monomial {m} is not covered by the products')
        pure[m] = diff
    used = set(pure)
    for p in products:
        used.update(bits(p.left1 | p.left2))
        used.update(h << LOW_BITS for h in bits(p.right1 | p.right2))
    for m in list(used):
        while m and m.bit_count() >= 2:
            used.add(m)
            m ^= 1 << (m.bit_length() - 1)
    cache = sorted(m for m in used if m.bit_count() >= 2)
    return Plan(tensor.addresses, BATCH, tensor.brot, LOW_BITS, products, pure, [], cache, parity_scratch=0)


def estimated_pairs(ell: int, width: int, dim: int) -> int:
    """Pairs a block of `ell` coordinates over `width` outputs needs, from the counting argument.

    E has codimension c in the ell*width ambient space. Every 2-dim subspace X contributes pairs from a
    space of dimension width - 2c, so E can be spanned only while 2 * (#X) * (width - 2c) >= ell*width - c.
    A block whose ambient space is no larger than its slices gets no saving and costs half its ambient.
    """
    ambient = ell * width
    if ell < 2 or ambient <= dim:
        return -(-ambient // 2)
    count = (2 ** ell - 1) * (2 ** ell - 2) // 6
    c = 0
    while 2 * count * (width - 2 * (c + 1)) >= ambient - (c + 1) and ambient - (c + 1) >= dim:
        c += 1
    return -(-(ambient - c) // 2)


def compositions(total: int, parts: tuple[int, ...]):
    if total == 0:
        yield ()
        return
    for part in parts:
        if part <= total:
            for rest in compositions(total - part, parts):
                yield (part,) + rest


def monomial_groups(tensor: Tensor) -> list[tuple[list[int], int, int]]:
    """Low monomials grouped by the outputs their slices touch: (monomials, width, slice dimension)."""
    groups: dict[tuple, list[int]] = {}
    for low in range(1, 1 << LOW_BITS):
        block = Block(tensor, [low])
        groups.setdefault(gf2.canonical(block.outputs), []).append(low)
    out = []
    for key, monomials in groups.items():
        block = Block(tensor, monomials)
        out.append((monomials, len(key), len(gf2.span_basis(block.slices))))
    return out


def closure_size(monomials: list[int]) -> int:
    """Low slots a block needs if it used every monomial it holds at once."""
    return closure([m for m in monomials if m.bit_count() >= 2]).bit_count()


def candidate_blocks(tensor: Tensor, rng: random.Random, attempt: int, sizes: tuple[int, ...],
                     slots: int = 11) -> list[list[int]]:
    """Blocks of low monomials. Attempt 0 takes the cheapest estimated split; later attempts shuffle.

    A block whose monomials would need more low slots than the width gate leaves is not offered.
    """
    blocks = []
    for monomials, width, dim in monomial_groups(tensor):
        monomials = list(monomials)
        options = sorted(compositions(len(monomials), sizes),
                         key=lambda c: (sum(estimated_pairs(n, width, dim) for n in c), len(c)))
        if not options:
            options = [(len(monomials),)]
        if attempt:
            monomials = rng.sample(monomials, len(monomials))
            options = options[:3]
        parts = options[0] if attempt == 0 else rng.choice(options)
        at = 0
        for n in parts:
            block = sorted(monomials[at:at + n])
            if closure_size(block) > slots:
                raise WidthGateError(f'low monomials {block} need {closure_size(block)} slots; {slots} fit')
            blocks.append(block)
            at += n
    return blocks


def plan_from_blocks(tensor: Tensor, blocks: list[list[int]], rng: random.Random, restarts: int, memo: dict):
    products, info = [], []
    for monomials in blocks:
        key = tuple(monomials)
        if key not in memo:
            block = Block(tensor, monomials)
            made, first_phase = block.solve(rng, restarts)
            memo[key] = (made, dict(monomials=monomials, outputs=block.width, first_phase=first_phase,
                                    slice_dim=len(gf2.span_basis(block.slices)), products=len(made),
                                    attempts=block.attempts))
        made, one = memo[key]
        products += made
        info.append(one)
    return assemble(tensor, products), info


# --- schedule with the width gate -----------------------------------------------------------------

def min_capacity(plan: Plan) -> int:
    """Low slots the largest single demand needs: one product's controls or one pure correction's chain."""
    need = [r.bit_count() for r in requirements(plan)]
    need += [closure([m]).bit_count() for m in pure_monomials(plan)]
    return max(need + [1])


def schedule_within_width(plan: Plan, max_width: int, rng: random.Random, effort: int):
    """Cheapest cache schedule that fits. Raises WidthGateError, and builds nothing, when none does."""
    fixed = fixed_width(plan.addresses, plan.brot, high_cache_size(plan), plan.batch)
    top = min(11, max_width - fixed)
    low = min_capacity(plan)
    if top < low:
        raise WidthGateError(f'plan needs {low} low slots; {top} fit in {max_width} qubits ({fixed} are fixed)')
    best = None
    for capacity in range(low, top + 1):
        schedule = search_schedule(plan, capacity, rng, effort)
        if best is None or schedule['low_computations'] < best['low_computations']:
            best = schedule
        if best['low_computations'] <= lower_bound(plan):
            break
    check_width(plan, best['capacity'], max_width)
    return best


def toffolis(plan: Plan, schedule: dict) -> int:
    return high_cache_size(plan) + schedule['low_computations'] + len(plan.products)


def plan_delta(delta, brot: int, config: PlannerConfig = PlannerConfig()) -> PlanResult:
    """The cheapest plan and schedule found for one delta table, exact and within `config.max_width`.

    Raises WidthGateError, with no plan returned and no circuit built, when no candidate fits.
    """
    started = time.time()
    slots = precheck_width(len(delta), brot, config.max_width)
    tensor = build_tensor(delta, brot)
    rng = random.Random(config.seed)
    memo: dict = {}
    candidates, rejected = [], 0
    for attempt in range(max(1, config.partitions)):
        try:
            blocks = candidate_blocks(tensor, rng, attempt, config.sizes, slots)
        except WidthGateError:
            rejected += 1
            continue
        candidates.append(plan_from_blocks(tensor, blocks, rng, config.restarts, memo))
    best = None
    for plan, info in sorted(candidates, key=lambda c: len(c[0].products)):
        if best and len(plan.products) + high_cache_size(plan) + lower_bound(plan) >= best[0]:
            break
        try:
            schedule = schedule_within_width(plan, config.max_width, rng, config.schedule_effort)
        except WidthGateError:
            rejected += 1
            continue
        cost = toffolis(plan, schedule)
        if best is None or cost < best[0]:
            best = (cost, plan, schedule, info)
    if best is None:
        raise WidthGateError(f'no candidate plan fits {config.max_width} qubits ({rejected} rejected); '
                             'nothing was emitted')
    cost, plan, schedule, info = best
    assert_independent(plan, delta)
    check_width(plan, schedule['capacity'], config.max_width)
    report = dict(toffolis=cost, qubits=peak_width(plan, schedule['capacity']), products=len(plan.products),
                  high_cache=high_cache_size(plan), low_computations=schedule['low_computations'],
                  capacity=schedule['capacity'], outputs=tensor.outputs, rejected_width=rejected,
                  blocks=info, seconds=round(time.time() - started, 2))
    return PlanResult(plan, schedule, report)


def plan_words(words, brot: int, config: PlannerConfig = PlannerConfig()) -> list[PlanResult]:
    """One result per batch of five words (the XOR chain of `paired_anf.batch_deltas`)."""
    return [plan_delta(delta, brot, config) for delta in batch_deltas(words, BATCH)]
