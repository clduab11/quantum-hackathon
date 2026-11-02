# SPDX-License-Identifier: Apache-2.0
"""Phased low-monomial cache schedules.

`scheduler.make_schedule` orders the products by a few heuristics and appends every pure-low correction
at the end, so each pure monomial that was dropped earlier is computed again. Pure-low corrections are
plain CNOT fanouts that commute with every product, so they can ride along with any phase whose cache
holds their monomial. This module orders the distinct requirement masks by local search, runs the same
exact retention DP over them, and then places each pure monomial in a phase that already holds it.
The result is an ordinary schedule dict: `scheduler.audit` and `emitter.build_staged` take it unchanged.
"""
from __future__ import annotations

import random

import numpy as np

from tasks.dfthcsos.full_xor.paired_anf import Plan
from tasks.dfthcsos.full_xor.scheduler import INDEX, audit, closure, requirements, states_and_cost


def pure_monomials(plan: Plan) -> list[int]:
    return sorted((m for m, v in plan.pure.items() if v and m < 16 and m.bit_count() >= 2), reverse=True)


class Retention:
    """Exact retention DP for one capacity: cheapest closed cache states for a sequence of masks."""

    INF = np.int32(1_000_000)

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.states, self.cost = states_and_cost(capacity)
        self._dest: dict[int, np.ndarray] = {}

    def dest(self, mask: int) -> np.ndarray:
        if mask not in self._dest:
            self._dest[mask] = np.flatnonzero((self.states & mask) == mask)
        return self._dest[mask]

    def run(self, masks: list[int], backtrack: bool = False):
        """(computations, states per mask). The states are None unless `backtrack`."""
        count = len(self.states)
        dp = np.full(count, self.INF, dtype=np.int32)
        dp[0] = 0
        backs = []
        for mask in masks:
            dest = self.dest(mask)
            values = dp[:, None] + self.cost[:, dest]
            old = np.argmin(values, axis=0)
            new = np.full(count, self.INF, dtype=np.int32)
            new[dest] = values[old, np.arange(len(dest))]
            if backtrack:
                back = np.full(count, -1, dtype=np.int32)
                back[dest] = old
                backs.append(back)
            dp = new
        end = int(np.argmin(dp))
        total = int(dp[end])
        if not backtrack:
            return total, None
        chosen = []
        for back in reversed(backs):
            chosen.append(int(self.states[end]))
            end = int(back[end])
        chosen.reverse()
        return total, chosen


def phased_schedule(plan: Plan, mask_order: list[int], retention: Retention, label: str = 'phased') -> dict:
    """Schedule the distinct requirement masks in `mask_order`, then place the pure-low corrections."""
    capacity = retention.capacity
    req = requirements(plan)
    groups: dict[int, list[int]] = {}
    for index, mask in enumerate(req):
        groups.setdefault(mask, []).append(index)
    if sorted(mask_order) != sorted(groups):
        raise ValueError('mask order is not a permutation of the requirement masks')
    if any(mask.bit_count() > capacity for mask in groups):
        raise ValueError('one product requires more low products than capacity')
    pure = pure_monomials(plan)
    extra: list[int] = []
    while True:
        masks = list(mask_order) + [closure([m]) for m in extra]
        total, states = retention.run(masks, backtrack=True)
        held = states[:len(mask_order)]
        missing = [m for m in pure if m not in extra and not any((s >> INDEX[m]) & 1 for s in held)]
        if not missing:
            break
        extra += missing
    events, order = [], []
    placed = set()
    for mask, state in zip(mask_order, held):
        events.append(dict(kind='products', indices=list(groups[mask]), required=mask, cache=state))
        order += groups[mask]
        for m in pure:
            if m not in placed and m not in extra and (state >> INDEX[m]) & 1:
                events.append(dict(kind='pure_low', monomial=m, required=closure([m]), cache=state))
                placed.add(m)
    for m, state in zip(extra, states[len(mask_order):]):
        events.append(dict(kind='pure_low', monomial=m, required=closure([m]), cache=state))
    schedule = dict(label=label, capacity=capacity, product_order=order, events=events, low_computations=total,
                    min_live_required=max([m.bit_count() for m in groups] + [0]),
                    peak_live=max([int(s).bit_count() for s in states] + [0]))
    audit(plan, schedule)
    return schedule


def lower_bound(plan: Plan) -> int:
    """Low monomials any schedule must compute at least once."""
    need = closure(pure_monomials(plan))
    for mask in requirements(plan):
        need |= mask
    return need.bit_count()


def search_schedule(plan: Plan, capacity: int, rng: random.Random, iterations: int = 300) -> dict:
    """Best phased schedule found: greedy start, then swap and move local search over the mask order."""
    retention = Retention(capacity)
    masks = sorted(set(requirements(plan)))
    floor = lower_bound(plan)
    # Greedy start: always take the mask that costs the fewest new monomials next.
    remaining, now, order = set(masks), 0, []
    while remaining:
        mask = min(remaining, key=lambda r: ((r & ~now).bit_count(), -r.bit_count(), r))
        order.append(mask)
        remaining.remove(mask)
        now = mask
    best, best_cost = order, retention.run(order)[0]
    for _ in range(iterations):
        if best_cost <= floor or len(best) < 2:
            break
        trial = list(best)
        i, j = rng.sample(range(len(trial)), 2)
        if rng.random() < 0.5:
            trial[i], trial[j] = trial[j], trial[i]
        else:
            trial.insert(j, trial.pop(i))
        cost = retention.run(trial)[0]
        if cost <= best_cost:
            best, best_cost = trial, cost
    return phased_schedule(plan, best, retention)
