"""90-qubit invsqrt schedule: deferred feed-forward and a Gray curvature checkpoint.

Method parent (Apache-2.0): Kozykorpesh, Quantum AI LB score, V3 run 361677445,
https://www.kaggle.com/code/kozykappa/quantum-ai-lb-score-6-68108?scriptVersionId=361677445
The positive-Davio reload orders below are the method parameters published in
anazemcev, Quantum Circuits | Source & Exact Compilation v4 (Apache-2.0).
They are not a coefficient dataset. Arithmetic helpers come from our
signed-digit generator. The pruned shift is the Dmitrii Gluzdov V6 boundary
rule as that schedule names it (run 361592338). His notebook is not attached
and is not loaded. Direct reuse waits on PRA-205. This file is a port.

Coefficients are the caller's own fitted table.
"""

from __future__ import annotations

from fractions import Fraction
from functools import lru_cache

import numpy as np
import kickmix as km

from tasks.invsqrt import signed_digit as sd

# Published Davio orders for the two curvature bits this schedule reloads
# (checkpoint at bit 5, curve_count 2). `ands` is the node count we recompute.
CURVATURE_CHOICES = {
    "curve5": {"ands": 8, "order": (0, 7, 6, 5, 1, 2, 3, 4), "polarity": 61},
    "curve6": {"ands": 9, "order": (5, 4, 7, 2, 1, 0, 3, 6), "polarity": 249},
}
SELECTED_OPTIONS = {
    "delay_high": True,
    "gray_checkpoint": True,
    "curve_count": 2,
    "late_coarse": 0,
}


def mobius_transform(table: list[int]) -> list[int]:
    """Truth table to algebraic normal form over GF(2), packed in integers."""
    result = [int(value) for value in table]
    if not result or len(result) & (len(result) - 1):
        raise ValueError("truth-table length must be a power of two")
    width = (len(result) - 1).bit_length()
    for bit in range(width):
        step = 1 << bit
        for start in range(0, len(result), 2 * step):
            for offset in range(step):
                result[start + step + offset] ^= result[start + offset]
    return result


def optimized_shift(builder, flags, word, length, inverse, prune=True):
    """Shift `word` by the normalization flags. Empty high targets use AND, not CSWAP."""
    stages = [(1, 1), (2, 2), (3, 4), (4, 8)]
    occupied = []
    width = length
    for stage, amount in stages:
        occupied.append(min(width, length + 2) if prune and stage == 4 else width)
        width = min(width + amount, len(word))
    sequence = list(enumerate(stages))
    if inverse:
        sequence = sequence[::-1]
    for index, (stage, amount) in sequence:
        indices = range(occupied[index]) if inverse else reversed(range(occupied[index]))
        boundary = length + sum(step for _, step in stages[:index])
        for i in indices:
            if i + amount >= len(word):
                continue
            if i + amount >= boundary:
                if inverse:
                    builder.cx(word[i + amount], word[i])
                    builder.del_and(flags[stage], word[i], word[i + amount])
                else:
                    builder.init_and(flags[stage], word[i], word[i + amount])
                    builder.cx(word[i + amount], word[i])
            else:
                builder.cswap(flags[stage], word[i], word[i + amount])


def _xor_many_toffoli(builder, left, right, targets):
    targets = list(targets)
    if not targets:
        return
    first = targets[0]
    for target in targets[1:]:
        builder.cx(first, target)
    builder.ccx(left, right, first)
    for target in reversed(targets[1:]):
        builder.cx(first, target)


def init_anf(builder, table, address, target, borrowed=()):
    """XOR the table into `target`. Leaf products land on the output wires."""
    address, target = list(address), list(target)
    width = len(address)
    coefficient = mobius_transform(table)
    loan = list(borrowed)[: max(0, width - 2)]
    extra = list(builder.alloc_qubits(max(0, width - 2) - len(loan)))
    scratch = loan + extra

    def emit(mask, control):
        outputs = [target[j] for j in range(len(target)) if (coefficient[mask] >> j) & 1]
        if not outputs:
            return
        if control is None:
            builder.x(km.array(outputs))
        else:
            builder.cx(control, km.array(outputs))

    def walk(mask, last, control):
        emit(mask, control)
        for bit in range(last + 1, width):
            child = mask | (1 << bit)
            if not mask:
                walk(child, bit, address[bit])
            elif bit == width - 1:
                outputs = [target[j] for j in range(len(target)) if (coefficient[child] >> j) & 1]
                _xor_many_toffoli(builder, control, address[bit], outputs)
            else:
                qubit = scratch[mask.bit_count() - 1]
                builder.init_and(control, address[bit], qubit)
                walk(child, bit, qubit)
                builder.del_and(control, address[bit], qubit)

    walk(0, -1, None)
    if extra:
        builder.free(km.array(extra))


def phase_from_records(builder, table, address, records):
    """Apply the deferred lookup phase once, after the address is free to borrow."""
    address, records = list(address), list(records)
    width = len(address)
    half = width // 2
    coefficient = mobius_transform(table)
    left = {1 << j: address[j] for j in range(half)}
    masks = [mask for mask in range(1, 1 << half) if mask.bit_count() > 1]
    scratch = list(builder.alloc_qubits(len(masks) + width - half - 1))
    for mask, qubit in zip(masks, scratch):
        bit = mask.bit_length() - 1
        builder.init_and(left[mask ^ (1 << bit)], address[bit], qubit)
        left[mask] = qubit
    carry = scratch[len(masks):]
    parity = builder.alloc_bits(1)[0]

    def emit(high, high_qubit):
        for low in range(1 << half):
            value = coefficient[low | (high << half)]
            if not value:
                continue
            builder.bit_store(parity, False)
            while value:
                bit = (value & -value).bit_length() - 1
                builder.cx(records[bit], parity)
                value &= value - 1
            if not high and not low:
                builder.neg_if(parity)
                continue
            builder.push_condition(parity)
            if not low:
                builder.z(high_qubit)
            elif not high:
                builder.z(left[low])
            else:
                builder.cz(left[low], high_qubit)
            builder.pop_condition()

    def walk(mask, last, qubit):
        emit(mask, qubit)
        for index in range(last + 1, width - half):
            child = mask | (1 << index)
            if not mask:
                walk(child, index, address[half + index])
            else:
                temp = carry[mask.bit_count() - 1]
                builder.init_and(qubit, address[half + index], temp)
                walk(child, index, temp)
                builder.del_and(qubit, address[half + index], temp)

    walk(0, -1, None)
    for mask in reversed(masks):
        bit = mask.bit_length() - 1
        builder.del_and(left[mask ^ (1 << bit)], address[bit], left[mask])
    builder.free(km.array(scratch))
    builder.free(parity)


@lru_cache(maxsize=None)
def _plan_cache(values: tuple, order: tuple, polarity: int):
    return boolean_plan(values, order, polarity)


def boolean_plan(values, order=(7, 4, 2, 3, 0, 1, 6, 5), polarity=104):
    """Positive Davio XOR/AND graph. Algebra only; no sampling."""
    values = list(values)
    width = len(order)
    indices = np.arange(1 << width)
    original = sum((((indices >> j) & 1) << order[j]) for j in range(width)) ^ polarity
    packed = np.packbits(np.asarray(values, dtype=np.uint8)[original], bitorder="little")
    truth = int.from_bytes(packed.tobytes(), "little")
    nodes = []
    node_ids = {}

    def xor(left, right):
        return (left[0] ^ right[0], left[1] ^ right[1])

    @lru_cache(maxsize=None)
    def rec(node, level):
        ones = (1 << (1 << level)) - 1
        if node == 0:
            return (0, frozenset())
        if node == ones:
            return (1, frozenset())
        half = (1 << (1 << (level - 1))) - 1
        low = node & half
        high = node >> (1 << (level - 1))
        left = rec(low, level - 1)
        right = rec(low ^ high, level - 1)
        if not right[1]:
            return xor(left, (0, frozenset((level - 1,)))) if right[0] else left
        key = (level - 1, right)
        if key not in node_ids:
            node_ids[key] = width + len(nodes)
            nodes.append(key)
        return xor(left, (0, frozenset((node_ids[key],))))

    result = rec(truth, width)
    return {"order": tuple(order), "polarity": polarity, "nodes": list(nodes), "result": result}


def restore_boolean(builder, plan, address, target):
    """Write one addressed bit with the Davio graph, then uncompute the nodes."""
    address = list(address)
    width = len(address)
    flipped = [address[j] for j in range(width) if (plan["polarity"] >> j) & 1]
    if flipped:
        builder.x(km.array(flipped))
    wires = [address[j] for j in plan["order"]]
    nodes = list(builder.alloc_qubits(len(plan["nodes"])))
    parity = builder.alloc_qubits(1)[0]
    wires.extend(nodes)

    def form(expression):
        if expression[0]:
            builder.x(parity)
        for index in sorted(expression[1]):
            builder.cx(wires[index], parity)

    for index, (variable, right) in enumerate(plan["nodes"]):
        form(right)
        builder.init_and(wires[variable], parity, nodes[index])
        form(right)
    constant, terms = plan["result"]
    if constant:
        builder.x(target)
    for term in sorted(terms):
        builder.cx(wires[term], target)
    for index in reversed(range(len(nodes))):
        variable, right = plan["nodes"][index]
        form(right)
        builder.del_and(wires[variable], parity, nodes[index])
        form(right)
    if nodes:
        builder.free(km.array(nodes))
    builder.free(parity)
    if flipped:
        builder.x(km.array(flipped))


def _choice(name, values):
    choice = CURVATURE_CHOICES[name]
    plan = _plan_cache(tuple(int(v) for v in values), tuple(choice["order"]), int(choice["polarity"]))
    if len(plan["nodes"]) != choice["ands"]:
        raise RuntimeError(f"{name} Davio node count {len(plan['nodes'])} != {choice['ands']}")
    return plan


def build_raw(cfg, tables):
    """Build the selected 90-qubit schedule from `cfg` and fitted `tables`."""
    if (cfg.f2, cfg.f1, cfg.fyr, cfg.gy, sorted(cfg.drop2)) != (8, 19, 27, 1, [5]):
        raise ValueError("This schedule is for Cfg(8, 19, 27, 1, drop 5)")
    options = SELECTED_OPTIONS
    place = sd.layout(cfg, tables)
    if (place["w1"], place["LB"], place["S"], place["whi"]) != (18, 21, 20, 8):
        raise RuntimeError(f"Unexpected layout {place['w1'], place['LB'], place['S'], place['whi']}")
    split, bounds = sd.prepare_derivative_split(sd, cfg, tables)
    builder = km.CircuitBuilder()
    register = builder.create_quantum_register(22, name="x")
    flags = builder.alloc_qubits(5)
    sd.normalize(builder, register, flags)
    builder.x(register[-1])
    late = options["late_coarse"]
    c2, residual, coarse, low, high = [
        builder.alloc_qubits(n) for n in (cfg.w2, 12, 7 - late, 21, 8)
    ]
    full_target = km.array(list(low) + list(residual) + list(c2) + list(high) + list(coarse))
    full_table = [0] * 256
    rest_table = [0] * 256
    high_table = [0] * 256
    low_table = [0] * 256
    for (parity, address), (k2, _, _) in tables.items():
        key = (parity, address)
        index = address + 128 * parity
        common = place["lo"][key] | (split["residual"][key] << 21) | (k2 << 33)
        full_table[index] = common | (place["hi"][key] << (33 + cfg.w2)) | (split["coarse"][key] << (41 + cfg.w2))
        rest_table[index] = split["residual"][key] | (k2 << 12) | (split["coarse"][key] << (12 + cfg.w2))
        high_table[index] = place["hi"][key]
        low_table[index] = place["lo"][key]
    address = km.array(list(register[14:21]) + [flags[0]])
    delta = register[:14]
    extra_borrow = []

    def erase(reg, table):
        bits = builder.alloc_bits(len(reg))
        builder.hmr(reg, bits)
        return list(bits), list(table)

    def phase(reg, low_bit):
        extension = builder.alloc_qubits(9)
        word = km.array(list(reg) + list(extension) + [register[-1]])
        optimized_shift(builder, flags, word, len(reg), False, prune=True)
        for index, qubit in enumerate(word):
            exponent = low_bit + index - cfg.fy - 10
            if exponent < 0:
                builder.z_pow(qubit, Fraction(2) ** (exponent + 1))
        optimized_shift(builder, flags, word, len(reg), True, prune=True)
        builder.free(extension)

    def adder(source, target, cin=None, sub=False):
        sd.folded_gadd(builder, source, target, cin, sub, borrowed=(register[-1], *extra_borrow))

    def inner(inverse):
        rows = cfg.rrow_list()
        for index in reversed(rows) if inverse else rows:
            shift = cfg.sh2[index]
            if shift >= 0:
                addend, target, carry = c2[shift:], residual, (c2[shift - 1] if shift else None)
            else:
                addend, target, carry = c2, residual[-shift:], None
            builder.cx(delta[index], target)
            adder(addend, target, carry, sub=inverse)
            builder.cx(delta[index], target)

    def outer(derivative, inverse):
        for index in range(14) if inverse else reversed(range(14)):
            shift = cfg.sh1[index]
            carry = derivative[shift - 1] if shift else None
            builder.cx(delta[index], low)
            adder(derivative[shift:], low, carry, sub=inverse)
            builder.cx(delta[index], low)

    init_anf(builder, full_table, address, full_target, borrowed=(register[-1],))
    if not all(value >> 7 == 1 for value in high_table):
        raise RuntimeError("Constant-high carry borrowing proof failed")
    builder.x(high[-1])
    extra_borrow.append(high[-1])
    inner(False)
    extra_borrow.clear()
    builder.x(high[-1])
    if cfg.w2 != 7:
        raise RuntimeError("Curvature erasure is for a 7-bit coefficient")
    checkpoint_start = 7 - options["curve_count"]
    for index in range(checkpoint_start, 6):
        builder.cx(c2[index + 1], c2[index])
    erased = km.array(list(c2[checkpoint_start:]))
    checkpoint_table = []
    for index in range(256):
        coefficient = tables[(index // 128, index % 128)][0]
        coefficient ^= coefficient >> 1
        checkpoint_table.append(coefficient >> checkpoint_start)
    checkpoint_bits, _checkpoint_values = erase(erased, checkpoint_table)
    builder.free(erased)
    phase(high, 20)
    high_bits, _high_values = erase(high, high_table)
    builder.free(high)
    adder(residual[11:], coarse)
    derivative = residual[:11] + coarse
    outer(derivative, False)
    phase(low[cfg.gy:], cfg.gy)
    outer(derivative, True)
    low_bits, _low_values = erase(low, low_table)
    builder.free(low)
    replacement = builder.alloc_qubits(7 - checkpoint_start)
    c2 = km.array(list(c2[:checkpoint_start]) + list(replacement))
    curvature = np.array([tables[(index // 128, index % 128)][0] for index in range(256)], dtype=np.int64)
    gray = curvature ^ (curvature >> 1)
    reloads = 0
    for index in reversed(range(checkpoint_start, 7)):
        plan = _choice(f"curve{index}", (gray >> index) & 1)
        restore_boolean(builder, plan, address, c2[index])
        reloads += len(plan["nodes"])
        if index < 6:
            builder.cx(c2[index + 1], c2[index])
    adder(residual[11:], coarse, sub=True)
    inner(True)
    rest_target = km.array(list(residual) + list(c2) + list(coarse))
    rest_bits, _rest_values = erase(rest_target, rest_table)
    builder.free(rest_target)
    for offset, bit in enumerate(checkpoint_bits):
        index = checkpoint_start + offset
        builder.cx(bit, rest_bits[12 + index])
        if index < 6:
            builder.cx(bit, rest_bits[12 + index + 1])
    records = low_bits + rest_bits[: 12 + cfg.w2] + high_bits + rest_bits[12 + cfg.w2 :]
    if len(records) != len(full_target) + late:
        raise RuntimeError(f"Deferred record width {len(records)} != {len(full_target) + late}")
    phase_from_records(builder, full_table, address, records)
    builder.x(register[-1])
    sd.unnormalize(builder, register, flags)
    builder.free(flags)
    circuit = builder.finish_circuit()
    report = {
        "variant": "deferred_feedforward_gray_checkpoint",
        "options": options,
        "boolean_reload_toffoli": reloads,
        "qubits": circuit.num_qubits,
        "static_toffoli": int(circuit.operation_statistics().num_toffoli_like),
        "split_bounds": bounds,
        "provenance_method": "Apache-2.0 Kozykorpesh V3 run 361677445, port",
    }
    return circuit, report
