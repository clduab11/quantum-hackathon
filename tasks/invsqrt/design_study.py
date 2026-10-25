"""PRA-238 resource study, not a candidate circuit or shipment certificate.

The carry accumulator is an independent integer implementation of the prose
method in phucthaiv02's QCC portfolio (EXP-221). No notebook code or coefficient
file is loaded. Resource assumptions and limitations are in
docs/research/PRA-238-invsqrt-design-study.md.
"""

from __future__ import annotations

import json

from harness.costs import invsqrt_cost

REFERENCE_COST = 2_076_774
GATE_COST = REFERENCE_COST / 15


def resource_row(qubits, toffoli, synthesized_t, rotations=44):
    cost = invsqrt_cost(qubits, toffoli, synthesized_t)
    return dict(qubits=qubits, toffoli=toffoli, synthesized_t=synthesized_t,
                rotations=rotations, cost=cost, ratio=REFERENCE_COST / cost,
                clears_gate=cost <= GATE_COST)


def carry_step(low, carry, term, width):
    """Accumulate a signed term, preserving the unbounded integer exactly."""
    quotient, low = divmod(low + term, 1 << width)
    return low, carry + quotient


def carry_certificate(width=15, chunk_size=131072):
    """Check all x and every prefix of the eleven narrow outer rows.

    The three wide rows run first, as in schedule90. The low word then splits
    into a width-bit accumulator and its untouched upper word. The carry
    counter starts at zero. Its signed range must fit two bits before folding.
    This proves integer regrouping, not quantum cleanup or calibrated phase.
    """
    import numpy as np
    from tasks.invsqrt import signed_digit as sd

    cfg, tables, _ = sd.load_or_build_tables()
    table = np.asarray([tables[(e, a)] for e in range(2) for a in range(128)], dtype=np.int64)
    place = sd.layout(cfg, tables)
    anchors = np.asarray([place["lo"][(e, a)] for e in range(2) for a in range(128)])
    minimum = maximum = failures = tested = max_term = 0
    final_min = final_max = overflow_inputs = 0
    first_overflow_x = None
    for start in range(1, sd.MAX_X + 1, chunk_size):
        xs = np.arange(start, min(start + chunk_size, sd.MAX_X + 1), dtype=np.int64)
        shifts = 22 - np.frexp(xs)[1].astype(np.int64)
        normalized = xs << shifts
        address = ((normalized >> 14) & 127) + 128 * (shifts & 1)
        delta = normalized & 16383
        k2, k1 = table[address, 0], table[address, 1]
        derivative, expected_sum = sd.pipeline(cfg, k2, k1, delta)
        word = anchors[address].copy()
        for i in (13, 12, 11):
            word -= (2 * ((delta >> i) & 1) - 1) * sd.rd(derivative, cfg.sh1[i])
        high, low = divmod(word, 1 << width)
        carry = np.zeros_like(low)
        for i in reversed(range(11)):
            term = -(2 * ((delta >> i) & 1) - 1) * sd.rd(derivative, cfg.sh1[i])
            max_term = max(max_term, int(np.max(np.abs(term))))
            low, carry = carry_step(low, carry, term, width)
            minimum = min(minimum, int(carry.min()))
            maximum = max(maximum, int(carry.max()))
        rebuilt = low + ((high + carry) << width)
        failures += int(np.count_nonzero(rebuilt != anchors[address] - expected_sum))
        final_min = min(final_min, int(carry.min()))
        final_max = max(final_max, int(carry.max()))
        bad = (carry < -2) | (carry > 1)
        overflow_inputs += int(np.count_nonzero(bad))
        if first_overflow_x is None and bad.any():
            first_overflow_x = int(xs[np.flatnonzero(bad)[0]])
        tested += len(xs)
    return dict(tested_inputs=tested, integer_failures=failures, width=width,
                narrow_rows=11, max_abs_term=max_term, min_prefix_carry=minimum,
                max_prefix_carry=maximum, final_min_carry=final_min,
                final_max_carry=final_max, two_bit_overflow_inputs=overflow_inputs,
                first_overflow_x=first_overflow_x,
                two_signed_bits_suffice=final_min >= -2 and final_max <= 1)


def model_rows():
    # Each 21-bit outer row costs 20 Toffolis, including its folded top carry.
    # Eleven 16-bit carry-out additions cost 16+1 (two-bit counter) each;
    # three full rows cost 20 each; folding the counter into five high bits costs 4.
    carry_saving = 2 * (14 * 20 - (11 * 17 + 3 * 20 + 4))
    # These are optimistic allowances, NOT measured new circuit resources:
    # 3 Cuccaro prefix positions on 3 wide rows, forward and backward: +18;
    # one shorter residual bit on 8 inner rows in each direction: -16.
    combined_toffoli = 1437.5 - carry_saving + 18 - 16
    # Transfer the *whole* stated EXP-222a/225a cost saving as an optimistic
    # equivalent budget. Margins, overlap, and transfer are not established.
    public_phase_credit = (141462 - 138095) / 82
    return {
        "baseline": resource_row(90, 1437.5, 1261),
        "carry_save_only": resource_row(92, 1437.5 - carry_saving, 1261),
        "carry_parity_prefix_assumed": resource_row(88, combined_toffoli, 1261),
        "combined_with_public_phase_credit_assumed": resource_row(88, combined_toffoli - public_phase_credit, 1261),
        "public_equivalent_at_our_assumed_peak": resource_row(88, 1365, 1276.4),
        "public_comparison_only": resource_row(82, 1365, 1276.4),
    }


def main():
    rejected = carry_certificate(15)
    certificate = carry_certificate(16)
    print(json.dumps({"gate_cost": GATE_COST, "rejected_15_bit": rejected,
                      "carry_certificate": certificate,
                      "models": model_rows()}, indent=2, sort_keys=True))
    return 0 if certificate["integer_failures"] == 0 and certificate["two_signed_bits_suffice"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
