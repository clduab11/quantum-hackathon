"""Cancel adjacent commuting involutions.

This file is a port of the method below. It is not independent authorship.

Method parent (Apache-2.0): the peephole used after rotation calibration in
Kozykorpesh, Quantum AI complete-domain affine compilation v2. Diagonal gates
and classical conditions are barriers. A match must be the same text within
the previous 256 live lines and must not cross a read/write conflict.
"""

from __future__ import annotations

import collections
import re

_QUBIT = re.compile(r"(?<!\w)q(\d+)")
_PHASE = {"Z", "CZ", "CCZ", "Z_POW"}
_GATES = {"X", "CX", "CCX", "SWAP", "CSWAP"}


def _touch(line: str):
    """Return (read, write) sets, or None when the line is a barrier."""
    parts = line.split()
    if not parts or "if" in parts:
        return None
    op = parts[0]
    if op not in _PHASE | _GATES:
        return None
    qubits = {int(match) for match in _QUBIT.findall(line)}
    if op in _PHASE:
        return qubits, set()
    if op == "X":
        return set(), qubits
    if op in {"CX", "CCX"}:
        ordered = [int(match) for match in _QUBIT.findall(line)]
        return set(ordered[:-1]), {ordered[-1]}
    if op == "SWAP":
        return qubits, qubits
    ordered = [int(match) for match in _QUBIT.findall(line)]
    return qubits, set(ordered[1:])


def optimize(text: str) -> tuple[str, dict]:
    """Return peephole text and a count of cancelled gate pairs."""
    kept: list[str | None] = []
    counts: collections.Counter = collections.Counter()
    for line in text.splitlines():
        if not line:
            continue
        described = _touch(line)
        op = line.split()[0]
        cancel = False
        if described is not None and op in _GATES:
            reads, writes = described
            for index in range(len(kept) - 1, max(-1, len(kept) - 257), -1):
                if kept[index] is None:
                    continue
                previous = kept[index]
                if previous == line:
                    kept[index] = None
                    counts[op] += 2
                    cancel = True
                    break
                earlier = _touch(previous)
                if earlier is None:
                    break
                earlier_reads, earlier_writes = earlier
                if writes & earlier_reads or earlier_writes & reads:
                    break
        if not cancel:
            kept.append(line)
    body = "\n".join(line for line in kept if line is not None)
    return body + "\n", dict(counts)
