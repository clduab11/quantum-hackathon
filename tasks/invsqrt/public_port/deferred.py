# SPDX-License-Identifier: Apache-2.0
"""Port of Dmitrii Gluzdov's Apache-2.0 notebook v7, scriptVersionId 361726742.

Source SHA-256 d689cc89f41a6c9130e9f4c3a6b08dfd5d758fcbbb79f527d55cbd3b48e15280.
https://www.kaggle.com/code/dmitriigluzdov/quantum-circuit-compilation-from-source?scriptVersionId=361726742
Credits: Sumit Chongder (centered polynomial), Rudra Bhaskar (split),
Gu/Kemeny/Yelin/Lukin (deferred repairs), Zongao Bian (virtual low bit),
and the authors named in tasks/invsqrt/PROVENANCE.md.
Local changes: package imports; reuse existing arithmetic helpers; remove
notebook setup, fitting drivers, saved-data replay and verifier calls.
"""
# Parent code cell 20.
import kickmix as km


def demolish(b, register):
    bits = b.alloc_bits(len(register))
    for q, m in zip(register, bits):
        b.hmr(q, m)
    return list(bits)

def repair_anf(b, address, table, measurements, low_bits=4):
    """Möbius-transform the truth table and share monomials of each half."""
    address = list(address)
    bits = list(measurements)
    coef = list(table)
    for i in range(len(address)):
        for mask in range(len(coef)):
            if mask & 1 << i:
                coef[mask] ^= coef[mask ^ 1 << i]

    def monomials(register):
        nodes = {1 << i: q for i, q in enumerate(register)}
        undo = []
        for mask in range(1, 1 << len(register)):
            if mask in nodes:
                continue
            bit = mask & -mask
            left = nodes[mask ^ bit]
            right = nodes[bit]
            target = b.alloc_qubits(1)[0]
            b.init_and(left, right, target)
            nodes[mask] = target
            undo.append((left, right, target))
        return (nodes, undo)
    lo, lundo = monomials(address[:low_bits])
    hi, hundo = monomials(address[low_bits:])
    one = b.alloc_qubits(1)[0]
    b.x(one)
    for mask, word in enumerate(coef):
        l = mask & (1 << low_bits) - 1
        h = mask >> low_bits
        while word:
            pos = (word & -word).bit_length() - 1
            b.push_condition(bits[pos])
            if l and h:
                b.cz(lo[l], hi[h])
            else:
                b.z(lo[l] if l else hi[h] if h else one)
            b.pop_condition()
            word &= word - 1
    b.x(one)
    b.free(one)
    for left, right, target in reversed(hundo + lundo):
        b.del_and(left, right, target)
        b.free(target)
    for bit in bits:
        b.free(bit)

