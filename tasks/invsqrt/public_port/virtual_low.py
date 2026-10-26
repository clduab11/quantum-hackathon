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
# Parent code cell 40.


def outer(b, add, derivative, low_suffix, delta, shifts, inverse):
    assert list(reversed(shifts)) == list(range(14))
    for i in range(14) if inverse else reversed(range(14)):
        sh = shifts[i]
        a0 = derivative[sh]
        cin = derivative[sh - 1] if sh else None
        a = derivative[sh + 1:]
        carry = b.alloc_qubits(1)[0]
        if cin is not None:
            b.cx(cin, a0)
        b.init_and(delta[i], a0, carry)
        if cin is not None:
            b.cx(cin, carry)
            b.cx(cin, a0)
        b.cx(delta[i], low_suffix)
        add(a, low_suffix, carry, sub=inverse)
        b.cx(delta[i], low_suffix)
        if cin is not None:
            b.cx(cin, a0)
            b.cx(cin, carry)
        b.del_and(delta[i], a0, carry)
        if cin is not None:
            b.cx(cin, a0)
        b.free(carry)
