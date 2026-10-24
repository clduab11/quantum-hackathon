"""Exact-domain affine rewrite for the invsqrt circuit.

This file is a port of the method below. It is not independent authorship.

Method parents (Apache-2.0), reimplemented here:
- Kozykorpesh, complete-domain affine compilation v2: linear GF(2) replacement
  of Toffoli and CSWAP, and reuse of qubit ids whose value is identically 0.
- anazemcev, source & exact compilation v4: measurement uncompute when the
  Toffoli result is an affine function of the other wires. The kickback is
  cancelled by one conditioned CZ. The conditional-Z affine-measurement
  variant is not used.

Every accepted replacement is checked against the full 3,133,452-input truth
vector. A sampled linear system only proposes a combination. Missed rewrites
are allowed. An invalid replacement is not.

Phase recorded here is the unconditional Z_POW and unconditional CZ/Z
contribution. Conditioned diagonals are kickback fixups and are not added.
"""

from __future__ import annotations

import collections
import heapq
import re
from decimal import Decimal
from fractions import Fraction

import numpy as np

MAX_X = 3_133_452
WORDS = (MAX_X + 63) // 64
_QUBIT = re.compile(r"(?<!\w)q(\d+)(?!\w)")
_BIT = re.compile(r"(?<!\w)b(\d+)(?!\w)")
_METADATA = {
    "REGISTER",
    "INFO_TAG",
    "APPEND_TO_REGISTER",
    "BIT_STORE0",
    "BIT_STORE1",
    "BIT_INVERT",
    "BIT_XOR",
}
_DIAGONAL = {"Z", "CZ", "CCZ", "Z_POW", "NEG"}


def _pack_input_bit(xs: np.ndarray, bit: int) -> np.ndarray:
    flags = ((xs >> bit) & 1).astype(np.uint8)
    packed = np.packbits(flags, bitorder="little")
    buffer = np.zeros(WORDS * 8, dtype=np.uint8)
    buffer[: len(packed)] = packed
    return np.ascontiguousarray(buffer.view(np.uint64)[:WORDS])


class CompiledCircuit:
    """Affine-compiled text plus the phase certificate collected on the way."""

    def __init__(self, text, phase, rotations, peak, rewrites, fresh_bits):
        self.text = text
        self.phase = phase
        self.rotations = rotations
        self.peak = peak
        self.rewrites = rewrites
        self.fresh_bits = fresh_bits


class DomainCompiler:
    def __init__(self, text: str):
        self.lines = [line for line in text.splitlines() if line]
        self.protected = set()
        for line in self.lines:
            if line.startswith("APPEND_TO_REGISTER"):
                self.protected.update(int(match) for match in _QUBIT.findall(line))
        if self.protected != set(range(22)):
            raise RuntimeError(f"Expected input qubits 0..21, found {sorted(self.protected)}")
        seen_bits = [int(match) for line in self.lines for match in _BIT.findall(line)]
        self.fresh_bit = 1 + max(seen_bits, default=-1)
        self.zero = np.zeros(WORDS, dtype=np.uint64)
        self.full = np.full(WORDS, np.uint64(2**64 - 1))
        if MAX_X % 64:
            self.full[-1] = np.uint64((1 << (MAX_X % 64)) - 1)
        self.full.setflags(write=False)
        self.zero.setflags(write=False)
        xs = np.arange(1, MAX_X + 1, dtype=np.uint64)
        self.original = [_pack_input_bit(xs, bit) for bit in range(22)]
        if int(self.original[0][0] & 1) != 1:
            raise RuntimeError("Input bit packing is not little-endian on x=1")
        self.values = {qubit: self.original[qubit] for qubit in range(22)}
        self.mapping = {qubit: qubit for qubit in range(22)}
        self.free: list[int] = []
        self.next_id = 22
        self.peak = 22
        self.depth = 0
        self.stack: list[dict] = []
        self.out: list[str] = []
        self.rewrites: collections.Counter = collections.Counter()
        self.phase = np.zeros(MAX_X, dtype=np.uint64)
        self.rotations: list[dict] = []
        self.sample = np.unique(
            np.r_[
                np.arange(min(8, WORDS)),
                np.linspace(0, WORDS - 1, 8, dtype=int),
            ]
        )
        self.false_candidates = 0

    def val(self, qubit: int):
        return self.values.get(qubit, self.zero)

    def canon(self, array: np.ndarray):
        if array is self.zero or array is self.full:
            return array
        if not array.any():
            return self.zero
        if np.array_equal(array, self.full):
            return self.full
        array.setflags(write=False)
        return array

    def equal(self, left, right) -> bool:
        if left is right:
            return True
        return bool(np.array_equal(left, right))

    def xor(self, left, right):
        if left is self.zero:
            return right
        if right is self.zero:
            return left
        if left is right:
            return self.zero
        return self.canon(np.bitwise_xor(left, right))

    def band(self, left, right):
        if left is self.zero or right is self.zero:
            return self.zero
        if left is self.full:
            return right
        if right is self.full or left is right:
            return left
        return self.canon(np.bitwise_and(left, right))

    def materialize(self, qubit: int) -> int:
        if qubit not in self.mapping:
            if self.free:
                self.mapping[qubit] = heapq.heappop(self.free)
            else:
                self.mapping[qubit] = self.next_id
                self.next_id += 1
                self.peak = self.next_id
        return self.mapping[qubit]

    def release(self):
        if self.depth:
            return
        for qubit in list(self.mapping):
            if qubit in self.protected:
                continue
            if self.val(qubit) is self.zero:
                heapq.heappush(self.free, self.mapping.pop(qubit))
                self.values.pop(qubit, None)

    def emit(self, line: str):
        def replace(match):
            qubit = int(match.group(1))
            return f"q{self.materialize(qubit)}"

        self.out.append(_QUBIT.sub(replace, line))

    def literal(self, function, excluded: set[int]):
        if function is self.zero or function is self.full:
            return None
        for qubit, value in self.values.items():
            if qubit not in excluded and self.equal(function, value):
                return qubit, False
        complement = self.xor(function, self.full)
        for qubit, value in self.values.items():
            if qubit not in excluded and self.equal(complement, value):
                return qubit, True
        return None

    def _signature(self, value, extra: list[int]) -> int:
        acc = 0
        for index in self.sample:
            acc = (acc << 64) | int(value[index])
        for index in extra:
            acc = (acc << 64) | int(value[index])
        return acc

    def linear_terms(self, function, excluded: set[int]):
        """Propose an affine combination on samples and prove it on every x."""
        if function is self.zero:
            return [], False
        if function is self.full:
            return [], True
        variables = [
            qubit
            for qubit, value in self.values.items()
            if qubit not in excluded and value is not self.zero and value is not self.full
        ]
        columns = [self.full] + [self.values[qubit] for qubit in variables]
        extra: list[int] = []
        for _attempt in range(8):
            basis = {}
            for index, value in enumerate(columns):
                vector = self._signature(value, extra)
                mask = 1 << index
                while vector:
                    pivot = vector.bit_length() - 1
                    if pivot not in basis:
                        basis[pivot] = (vector, mask)
                        break
                    existing, coeff = basis[pivot]
                    vector ^= existing
                    mask ^= coeff
            vector = self._signature(function, extra)
            mask = 0
            while vector:
                pivot = vector.bit_length() - 1
                if pivot not in basis:
                    return None
                existing, coeff = basis[pivot]
                vector ^= existing
                mask ^= coeff
            chosen = [index for index in range(len(columns)) if (mask >> index) & 1]
            exact = self.zero
            for index in chosen:
                exact = self.xor(exact, columns[index])
            if self.equal(exact, function):
                return [variables[index - 1] for index in chosen if index], (0 in chosen)
            self.false_candidates += 1
            mismatch = np.flatnonzero(np.not_equal(exact, function))
            if len(mismatch) == 0 or int(mismatch[0]) in extra:
                return None
            extra.append(int(mismatch[0]))
        return None

    def _clifford(self, target: int, terms, constant: bool) -> list[str]:
        lines = [f"X q{target}"] if constant else []
        lines.extend(f"CX q{qubit} q{target}" for qubit in terms)
        return lines

    def _add_phase(self, bits, units: int):
        if units == 0 or bits is self.zero:
            return
        if bits is self.full:
            self.phase += np.uint64(units)
            return
        flat = np.unpackbits(bits.view(np.uint8), bitorder="little")[:MAX_X]
        self.phase[flat.astype(bool)] += np.uint64(units)

    def _record_rotation(self, logical: int, theta: Fraction, bits):
        counted = (theta * 4).denominator != 1
        units = theta * (1 << 63)
        if units.denominator != 1:
            raise RuntimeError(f"Rotation {theta} is not on the 2^-64 lattice")
        flat = np.ones(MAX_X, dtype=np.uint8) if bits is self.full else (
            np.unpackbits(bits.view(np.uint8), bitorder="little")[:MAX_X].astype(np.uint8)
        )
        self.rotations.append(
            {
                "line": len(self.out),
                "logical": logical,
                "theta": theta,
                "counted": counted,
                "units": int(units),
                "bits": flat,
            }
        )

    def _conditioned(self, parts: list[str]) -> bool:
        return self.depth > 0 or "if" in parts

    def execute(self, line: str):
        parts = line.split()
        op = parts[0]
        if op in _METADATA:
            self.emit(line)
            return
        if op == "PUSH_CONDITION":
            self.stack.append(dict(self.values))
            self.depth += 1
            self.emit(line)
            return
        if op == "POP_CONDITION":
            before = self.stack.pop()
            self.depth -= 1
            if self.depth < 0:
                raise RuntimeError("Unbalanced POP_CONDITION")
            keys = set(before) | set(self.values)
            for qubit in keys:
                if not self.equal(self.val(qubit), before.get(qubit, self.zero)):
                    raise RuntimeError(f"Condition join changed q{qubit}")
            self.emit(line)
            self.release()
            return
        qubits = [int(match) for match in _QUBIT.findall(line)]
        if op in _DIAGONAL and self._conditioned(parts):
            if op == "Z_POW":
                raise RuntimeError(f"Conditioned rotation is outside this compiler: {line}")
            self.emit(line)
            return
        if "if" in parts and op not in _DIAGONAL:
            raise RuntimeError(f"Inline condition on {op} is unsupported: {line}")
        if op == "CCX":
            left, right, target = qubits
            product = self.band(self.val(left), self.val(right))
            replacement = None
            reason = None
            if product is self.zero:
                replacement, reason = [], "ccx_zero"
            elif product is self.full:
                replacement, reason = [f"X q{target}"], "ccx_one"
            else:
                found = self.literal(product, {target})
                if found is not None:
                    qubit, inverted = found
                    replacement = self._clifford(target, [qubit], inverted)
                    reason = "ccx_literal"
                else:
                    terms = self.linear_terms(product, {target})
                    if terms is not None:
                        variables, constant = terms
                        replacement = self._clifford(target, variables, constant)
                        reason = "ccx_affine"
            if replacement is None and self.depth == 0:
                result = self.xor(self.val(target), product)
                terms = None
                if result is self.zero:
                    terms = [], False
                elif result is self.full:
                    terms = [], True
                else:
                    found = self.literal(result, {target})
                    if found is not None:
                        qubit, inverted = found
                        terms = [qubit], inverted
                    else:
                        terms = self.linear_terms(result, {target})
                if terms is not None:
                    variables, constant = terms
                    prepare = self._clifford(target, variables, constant)
                    bit = self.fresh_bit
                    self.fresh_bit += 1
                    replacement = prepare + [
                        f"HMR q{target} b{bit}",
                        f"CZ q{left} q{right} if b{bit}",
                    ] + prepare
                    reason = "ccx_mbu"
            if replacement is None:
                self.emit(line)
            else:
                self.rewrites[reason] += 1
                for emitted in replacement:
                    self.emit(emitted)
            self.values[target] = self.xor(self.val(target), product)
            self.release()
            return
        if op == "CSWAP":
            control, left, right = qubits
            delta = self.xor(self.val(left), self.val(right))
            product = self.band(self.val(control), delta)
            replacement = None
            reason = None
            if product is self.zero:
                replacement, reason = [], "cswap_zero"
            elif self.equal(product, delta):
                replacement, reason = [f"SWAP q{left} q{right}"], "cswap_swap"
            else:
                found = self.literal(product, {left, right})
                if found is not None:
                    qubit, inverted = found
                    replacement = []
                    if inverted:
                        replacement += [f"X q{left}", f"X q{right}"]
                    replacement += [f"CX q{qubit} q{left}", f"CX q{qubit} q{right}"]
                    reason = "cswap_literal"
                else:
                    terms = self.linear_terms(product, {left, right})
                    if terms is not None:
                        variables, constant = terms
                        replacement = []
                        if constant:
                            replacement += [f"X q{left}", f"X q{right}"]
                        for qubit in variables:
                            replacement += [f"CX q{qubit} q{left}", f"CX q{qubit} q{right}"]
                        reason = "cswap_affine"
            if replacement is None:
                self.emit(line)
            else:
                self.rewrites[reason] += 1
                for emitted in replacement:
                    self.emit(emitted)
            self.values[left] = self.xor(self.val(left), product)
            self.values[right] = self.xor(self.val(right), product)
            self.release()
            return
        if op == "CX":
            control, target = qubits
            control_value = self.val(control)
            if control_value is self.zero:
                self.rewrites["cx_zero"] += 1
            elif control_value is self.full:
                self.rewrites["cx_one"] += 1
                self.emit(f"X q{target}")
            else:
                self.emit(line)
            self.values[target] = self.xor(self.val(target), control_value)
            self.release()
            return
        if op == "X":
            for qubit in qubits:
                self.values[qubit] = self.xor(self.val(qubit), self.full)
            self.emit(line)
            self.release()
            return
        if op == "SWAP":
            left, right = qubits
            self.values[left], self.values[right] = self.val(right), self.val(left)
            self.emit(line)
            self.release()
            return
        if op == "R":
            if all(self.val(qubit) is self.zero for qubit in qubits):
                self.rewrites["r_zero"] += 1
            else:
                self.emit(line)
            for qubit in qubits:
                self.values[qubit] = self.zero
            self.release()
            return
        if op == "HMR":
            self.emit(line)
            for qubit in qubits[:1]:
                self.values[qubit] = self.zero
            self.release()
            return
        if op == "Z_POW":
            theta = Fraction(Decimal(parts[2]))
            bits = self.val(qubits[0])
            if bits is self.zero:
                self.rewrites["zpow_zero"] += 1
            else:
                self._record_rotation(qubits[0], theta, bits)
                self.emit(line)
                units = theta * (1 << 63)
                self._add_phase(bits, int(units))
            self.release()
            return
        if op in {"Z", "CZ", "CCZ"}:
            product = self.full
            for qubit in qubits:
                product = self.band(product, self.val(qubit))
            units = 1 << 63
            if product is self.zero:
                self.rewrites[f"{op.lower()}_zero"] += 1
            else:
                self.emit(line)
                self._add_phase(product, units)
            self.release()
            return
        if op == "NEG":
            self.emit(line)
            self.phase += np.uint64(1 << 63)
            self.release()
            return
        raise RuntimeError(f"Unsupported operation: {line}")

    def compile(self) -> CompiledCircuit:
        for number, line in enumerate(self.lines, start=1):
            self.execute(line)
            if number % 4000 == 0:
                print(
                    f"affine {number}/{len(self.lines)} rewrites {sum(self.rewrites.values())} "
                    f"peak {self.peak} false {self.false_candidates}",
                    flush=True,
                )
        if self.depth or self.stack:
            raise RuntimeError("Unbalanced condition stack")
        for qubit in range(22):
            if not self.equal(self.val(qubit), self.original[qubit]):
                raise RuntimeError(f"Input q{qubit} was not restored")
        for qubit, value in self.values.items():
            if qubit not in self.protected and value is not self.zero:
                raise RuntimeError(f"Scratch q{qubit} was not restored")
        ids = list(self.mapping.values())
        if len(ids) != len(set(ids)):
            raise RuntimeError("Physical qubit map is not injective")
        text = "\n".join(self.out) + "\n"
        return CompiledCircuit(
            text,
            self.phase,
            self.rotations,
            self.peak,
            dict(self.rewrites),
            self.fresh_bit,
        )


def compile_circuit(circuit) -> CompiledCircuit:
    """Rewrite `circuit` and return text, phase and rotation activations."""
    return DomainCompiler(str(circuit)).compile()
