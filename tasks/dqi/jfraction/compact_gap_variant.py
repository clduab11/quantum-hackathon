# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Exact lifetime/flag compression around SomeJoint's public J-fraction decoder.

SomeJoint / Agniv Banerjee: Apache-2.0 decoder, arithmetic and gap/conversion
algorithm. Manwithacat: exact classical mask projection. Our additions:
sigma/inverse word sharing, an HMR-cleared mask-word reuse, and a coherent
four-flag codec. Upstream files and approximation policy remain unchanged.
"""
from __future__ import annotations

from contextlib import contextmanager

from .compact_lifetime_kernels import forney_reused_sigma, scale_active_reused_mask


def codec(builder, bits, *, inverse=False):
    """Map the8 no-adjacent-one four-bit words into3 bits, with fourth=0."""
    gates = (("cx", 3, 0), ("ccx", 0, 1, 3), ("cx", 3, 1),
             ("cx", 3, 2), ("ccx", 1, 2, 3))
    for gate in reversed(gates) if inverse else gates:
        getattr(builder, gate[0])(*(bits[i] for i in gate[1:]))


class GapBank:
    """Append chronological flags; temporarily decode only the accessed blocks.

    A completed block is an exact4-to3 encoding. All calls that change a flag
    preserve the no-adjacent-one invariant (forward toggle or reverse removal).
    Access unconditionally decodes/re-encodes a whole local block, so controls
    are the original flags, not a replacement approximation or measurement.
    """
    def __init__(self, builder, count):
        self.builder, self.count = builder, count
        self.blocks = {}
        self.encoded = set()
        self.appended = 0
        self.codec_calls = 0

    def _free(self, bits):
        from .common import km
        self.builder.free(km.array(bits))

    def append(self, index):
        assert index == self.appended and index < self.count
        block = index // 4
        self.blocks.setdefault(block, []).append(self.builder.alloc_qubits(1)[0])
        self.appended += 1

    def compress_completed(self, index):
        block = index // 4
        if index % 4 != 3:
            return
        assert block not in self.encoded and len(self.blocks[block]) == 4
        bits = self.blocks[block]
        codec(self.builder, bits)
        self.codec_calls += 1
        self._free([bits[3]])
        self.blocks[block] = bits[:3]
        self.encoded.add(block)

    @contextmanager
    def access(self, indices):
        indices = sorted(set(indices))
        assert all(0 <= i < self.appended for i in indices)
        opened = []
        for block in sorted({i // 4 for i in indices}):
            if block in self.encoded:
                bits = self.blocks[block] + [self.builder.alloc_qubits(1)[0]]
                codec(self.builder, bits, inverse=True)
                self.codec_calls += 1
                self.blocks[block] = bits
                self.encoded.remove(block)
                opened.append(block)
        try:
            yield {i: self.blocks[i // 4][i % 4] for i in indices}
        finally:
            for block in reversed(opened):
                bits = self.blocks[block]
                codec(self.builder, bits)
                self.codec_calls += 1
                self._free([bits[3]])
                self.blocks[block] = bits[:3]
                self.encoded.add(block)

    def release_zero(self):
        assert self.appended == self.count
        for bits in self.blocks.values():
            self._free(bits)
        self.blocks.clear()
        self.encoded.clear()


def extract_compact(builder, words, bank, *, reverse=False):
    from .jfraction_gap_decoder import reciprocal_active, rotate, toggle_gap
    slots = len(words) // 2
    assert bank.count == slots
    for j in reversed(range(slots)) if reverse else range(slots):
        if not reverse:
            bank.append(j)
        with bank.access([j - 1, j] if j else [j]) as flag:
            active = words[2 * j:]
            previous, gap = flag[j - 1] if j else False, flag[j]
            if not reverse:
                toggle_gap(builder, active, previous, gap)
            shortened = builder.alloc_qubits(1)[0]
            builder.cx(gap, shortened)
            if j:
                builder.cx(previous, shortened)
            rotate(builder, active, shortened, left=True)
            if reverse:
                reciprocal_active(builder, [1] + active[1:], shortened, reverse=True)
                scale_active_reused_mask(builder, active[0], active[1:], shortened, divide=False)
            else:
                scale_active_reused_mask(builder, active[0], active[1:], shortened, divide=True)
                reciprocal_active(builder, [1] + active[1:], shortened)
            rotate(builder, active, shortened, left=False)
            if j:
                builder.cx(previous, shortened)
            builder.cx(gap, shortened)
            builder.free(shortened)
            if reverse:
                toggle_gap(builder, active, previous, gap)
        if not reverse:
            bank.compress_completed(j)


def convert_compact(builder, words, bank, *, reverse=False):
    from .jfraction_decoder import conversion_layout, scale_words
    from .jfraction_gap_decoder import conversion_core, rotate, toggle_header
    p, q, stages = conversion_layout(words)
    stages = [(bank.count - 1 - i, *stage) for i, stage in enumerate(stages)]
    for j, x, y, old_p, old_q in reversed(stages) if reverse else stages:
        with bank.access([j - 1, j] if j else [j]) as flag:
            pending, gap = flag[j - 1] if j else False, flag[j]
            new_p = [x] + old_q[1:]
            rotations = [x, y] + old_q[1:]
            if reverse:
                rotate(builder, new_p, gap, left=True)
                scale_words(builder, x, old_q[1:], divide=True)
                toggle_header(builder, y, old_q, pending)
            else:
                if j:
                    builder.cswap(pending, x, y)
                rotate(builder, rotations, gap, left=True)
            conversion_core(builder, y, old_p, old_q, pending)
            if reverse:
                rotate(builder, rotations, gap, left=False)
                if j:
                    builder.cswap(pending, x, y)
            else:
                toggle_header(builder, y, old_q, pending)
                scale_words(builder, x, old_q[1:], divide=False)
                rotate(builder, new_p, gap, left=False)
    return p, q
