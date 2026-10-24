# SPDX-License-Identifier: Apache-2.0
# Modified extract of borrow_template from src/gen_dqi_v6/run_gu_port.py
# in the Apache-2.0 notebooks anazemcev v4 and kozykappa v2 (same bytes).
# This file keeps the affine route only. The notebook trie route is not copied.
# The loan is an approximate support claim. The official verifier is the test.
# No copyright year is added. See tasks/dqi/PROVENANCE.md.

"""Route two high template words into a 24-qubit scratch loan."""

from __future__ import annotations

import os


def borrow_template(builder, emitter, alloc, bm, d_width):
    """Loan template words 35 and 36, then return a restore closure.

    ``DQI_BORROW=affine`` selects one differing pivot and a six-AND ladder
    per modulo-37 class. The other routes stay available for measurement
    and are not the shipped default.
    """
    import gu_port as port

    bank = bm.final_bb_l

    def swaps(value):
        slot = (value + 2) % 37
        first = (slot + 35) % 37
        second = (slot + 36) % 37
        pairs = []
        if first != 35:
            pairs.append((35, first))
        if second == 35:
            second = first
        if second != 36:
            pairs.append((36, second))
        return pairs

    def route(reverse=False):
        with builder.phase("borrow/unroute" if reverse else "borrow/route"):
            mode = os.environ.get("DQI_BORROW")
            if mode != "affine":
                raise RuntimeError(f"shipped borrow route is affine, got {mode!r}")
            for slot in range(37):
                pairs = swaps(slot - 2)
                if not pairs:
                    continue
                values = [v & 255 for v in range(-1, 69) if (v + 2) % 37 == slot]
                if len(values) not in (1, 2):
                    raise RuntimeError(f"modulo-37 class {slot} has {len(values)} values")
                if len(values) == 2:
                    left, right = values
                    diff = left ^ right
                    pivot = (diff & -diff).bit_length() - 1
                    changed = [i for i in range(8) if i != pivot and (diff >> i) & 1]
                    for i in changed:
                        emitter.cx(d_width[pivot], d_width[i])
                    bits = [d_width[i] for i in range(8) if i != pivot]
                    target = 0
                    bit_index = 0
                    for i in range(8):
                        if i == pivot:
                            continue
                        bit = (left >> i) & 1
                        if i in changed:
                            bit ^= (left >> pivot) & 1
                        target |= bit << bit_index
                        bit_index += 1
                else:
                    changed = []
                    bits = d_width
                    target = values[0]
                with port.eq_test(emitter, bits, target) as control:
                    ordered = reversed(pairs) if reverse else pairs
                    for left_word, right_word in ordered:
                        emitter.swaps(control, port.word_pairs([bank[left_word]], [bank[right_word]]))
                for i in reversed(changed):
                    emitter.cx(d_width[pivot], d_width[i])

    route()
    loan = list(bank[35]) + list(bank[36])
    alloc.close("borrowed_template", loan)

    def restore():
        alloc.reopen("borrowed_template", loan)
        route(reverse=True)

    return restore
