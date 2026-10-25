# SPDX-License-Identifier: Apache-2.0
"""Exact XOR QROM with banked low addresses and bounded ANF traversal.

Method parents and module provenance: notices/30-dfthcsos.txt (PRA-232).
No notebook is executed and no external circuit or factor artifact is loaded.
"""
from __future__ import annotations

from functools import lru_cache
from operator import index

import numpy as np


def mobius(values):
    """Involutive GF(2) truth-table/ANF transform, with packed output columns."""
    result = list(map(int, values))
    if not result or len(result) & (len(result) - 1):
        raise ValueError('table length must be a power of two')
    stride = 1
    while stride < len(result):
        for start in range(0, len(result), 2 * stride):
            for j in range(stride):
                result[start + stride + j] ^= result[start + j]
        stride *= 2
    return result


def quantize_words(words, source_bits, brot):
    """Nearest-even integer rescaling, modulo a full turn; no factor refitting."""
    source_bits, brot = index(source_bits), index(brot)
    words = np.asarray(words)
    if not 1 <= brot <= source_bits <= 30:
        raise ValueError('require 1 <= brot <= source_bits <= 30')
    if not np.issubdtype(words.dtype, np.integer) or np.any(words < 0) or np.any(words >= 1 << source_bits):
        raise ValueError('angle words must be integers fitting source_bits')
    return np.rint(words / (1 << (source_bits - brot))).astype(np.int64) % (1 << brot)


def _xor_product(builder, left, right, targets):
    """One Toffoli fans a product into any number of arbitrary target bits."""
    if targets:
        pivot = targets[0]
        for q in targets[1:]:
            builder.cx(pivot, q)
        builder.ccx(left, right, pivot)
        for q in reversed(targets[1:]):
            builder.cx(pivot, q)


def _load(builder, values, address, outputs, scratch, pebble_degree):
    """Truncated ANF is exact on the legal prefix, including a partial bank."""
    import kickmix as km
    count, n = len(values), len(address)
    coefficients = mobius(values + [0] * ((1 << n) - count))
    coefficients[count:] = [0] * ((1 << n) - count)
    completed = mobius(coefficients)
    if completed[:count] != values:
        raise ArithmeticError('ANF completion changed a legal row')
    stats = dict(monomial_ands=0, recomputed_ands=0, direct_leaf_ands=0)

    @lru_cache(None)
    def children(mask, last):
        return tuple((mask | (1 << bit), bit) for bit in range(last + 1, n)
                     if mask | (1 << bit) < count)

    @lru_cache(None)
    def needed(mask, last):
        return max((1 + needed(child, bit) for child, bit in children(mask, last)
                    if children(child, bit)), default=0)

    def targets(mask):
        return [q for j, q in enumerate(outputs) if coefficients[mask] >> j & 1]

    def visit(mask, last, control, path, available):
        erased = []
        if mask.bit_count() == pebble_degree:
            deficit = max(0, needed(mask, last) - len(available))
            if deficit > max(0, len(path) - 1):
                raise ValueError('insufficient scratch for this pebbling degree')
            erased = path[:deficit]
            for a, b, q in reversed(erased):
                builder.del_and(a, b, q)
                available.append(q)
        selected = targets(mask)
        if selected:
            if control is None:
                builder.x(km.array(selected))
            else:
                builder.cx(control, km.array(selected))
        for child, bit in children(mask, last):
            if mask == 0:
                visit(child, bit, address[bit], path, available)
            elif not children(child, bit):
                selected = targets(child)
                _xor_product(builder, control, address[bit], selected)
                stats['direct_leaf_ands'] += bool(selected)
            else:
                if not available:
                    raise ValueError('insufficient traversal scratch')
                q = available.pop()
                builder.init_and(control, address[bit], q)
                stats['monomial_ands'] += 1
                visit(child, bit, q, path + [(control, address[bit], q)], available)
                builder.del_and(control, address[bit], q)
                available.append(q)
        for a, b, q in erased:
            available.remove(q)
            builder.init_and(a, b, q)
            stats['recomputed_ands'] += 1

    visit(0, -1, None, [], list(scratch))
    return completed, stats


def _erase(builder, table, address, bank):
    """Measure the bank and repair its phase using a split ANF polynomial.

    HMR resets bank qubits. Reuse them for low-half monomials and high-half
    traversal; all corrections are Clifford, conditioned on measurement parity.
    """
    import kickmix as km
    if not bank:
        return
    coefficients = mobius(table)
    n = len(address)
    records = builder.alloc_bits(len(bank))
    builder.hmr(km.array(bank), records)
    parity = builder.alloc_bits(1)[0]
    split = n // 2
    low_masks = [m for m in range(1, 1 << split) if m.bit_count() > 1]
    work_count = len(low_masks) + max(0, n - split - 1)
    extra = builder.alloc_qubits(max(0, work_count - len(bank)))
    work = list(bank) + list(extra)
    low = {1 << j: address[j] for j in range(split)}
    for mask, q in zip(low_masks, work):
        j = mask.bit_length() - 1
        builder.init_and(low[mask ^ (1 << j)], address[j], q)
        low[mask] = q
    carries = work[len(low_masks):]

    def emit(high, control):
        for lo in range(1 << split):
            value = coefficients[lo | high << split]
            if not value:
                continue
            builder.bit_store(parity, False)
            for j in range(len(bank)):
                if value >> j & 1:
                    builder.cx(records[j], parity)
            if not lo and not high:
                builder.neg_if(parity)
            else:
                builder.push_condition(parity)
                if not lo:
                    builder.z(control)
                elif not high:
                    builder.z(low[lo])
                else:
                    builder.cz(low[lo], control)
                builder.pop_condition()

    def visit(mask, last, control):
        emit(mask, control)
        for bit in range(last + 1, n - split):
            child = mask | 1 << bit
            if not mask:
                visit(child, bit, address[split + bit])
            else:
                q = carries[mask.bit_count() - 1]
                builder.init_and(control, address[split + bit], q)
                visit(child, bit, q)
                builder.del_and(control, address[split + bit], q)
    visit(0, -1, None)
    for mask in reversed(low_masks):
        j = mask.bit_length() - 1
        builder.del_and(low[mask ^ (1 << j)], address[j], low[mask])
    builder.free(extra)
    builder.free(records)
    builder.free(parity)


def build_qrom(delta, brot, *, bank_bits=1, scratch=6, pebble_degree=5):
    """Build one exact XOR-difference oracle; return circuit and resource report.

    bank_bits 0/1/2 selects direct/two-address/four-address lookup. Zero
    difference columns are omitted. The fixed cap is enforced on every circuit.
    No state or ordering depends on a verifier salt or simulation outcome.
    """
    import kickmix as km
    delta = np.asarray(delta)
    brot, bank_bits, scratch, pebble_degree = map(index, (brot, bank_bits, scratch, pebble_degree))
    if delta.ndim != 2 or delta.shape[0] < 2 or delta.shape[1] < 1:
        raise ValueError('delta must be a nonempty (addresses >= 2, words) table')
    if not 1 <= brot <= 30 or not np.issubdtype(delta.dtype, np.integer):
        raise ValueError('require integer words and 1 <= brot <= 30')
    if np.any(delta < 0) or np.any(delta >= 1 << brot):
        raise ValueError('word outside brot range')
    if bank_bits not in (0, 1, 2) or scratch < 1 or pebble_degree < 2:
        raise ValueError('invalid bank_bits, scratch or pebble_degree')
    rows, batch = delta.shape
    n = (rows - 1).bit_length()
    bank_bits = min(bank_bits, n)
    width, banks = batch * brot, 1 << bank_bits
    packed = [sum(int(v) << (j * brot) for j, v in enumerate(row)) for row in delta]
    packed += [0] * ((-rows) % banks)
    coefficients = [mobius(packed[i:i+banks]) for i in range(0, len(packed), banks)]
    active = [(s, bit) for s in range(1, banks) for bit in range(width)
              if any(row[s] >> bit & 1 for row in coefficients)]
    if n + width + len(active) + scratch > 128:
        raise ValueError('ANGLE qubit cap exceeded by requested layout')
    values = [row[0] | sum(((row[s] >> bit) & 1) << (width+j)
                          for j, (s, bit) in enumerate(active)) for row in coefficients]
    b = km.CircuitBuilder()
    sel = list(b.create_quantum_register(n, 'selection'))
    outputs = [q for j in range(batch) for q in b.create_quantum_register(brot, f'word_{j}')]
    bank = list(b.alloc_qubits(len(active)))
    work = b.alloc_qubits(scratch)
    completed, stats = _load(b, values, sel[bank_bits:], outputs + bank, list(work), pebble_degree)
    b.free(work)
    both = None
    if any(s == 3 for s, _ in active):
        both = b.alloc_qubits(1)[0]
        b.init_and(sel[0], sel[1], both)
    for q, (s, bit) in zip(bank, active):
        control = both if s == 3 else sel[s.bit_length()-1]
        b.ccx(control, q, outputs[bit])
    if both is not None:
        b.del_and(sel[0], sel[1], both)
        b.free(both)
    _erase(b, [v >> width for v in completed], sel[bank_bits:], bank)
    b.free(km.array(bank))
    circuit = b.finish_circuit()
    if circuit.num_qubits > 128:
        raise ValueError('ANGLE qubit cap exceeded during bank erasure')
    return circuit, dict(num_qubits=int(circuit.num_qubits),
                         toffoli_per_call=int(circuit.operation_statistics().num_toffoli_like),
                         bank_bits=bank_bits, bank_width=len(active), scratch=scratch,
                         pebble_degree=pebble_degree, **stats)
