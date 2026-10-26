# SPDX-License-Identifier: Apache-2.0
# Port of SomeJoint v7; see PROVENANCE.md and SOURCE_MAP.json.
# Praxen: package imports; production functions only; no notebook runtime.
"P1 candidate: fixed-grade Bezoutian transform plus root-test-only scan.\n\nApproximation: unresolved interior Euclidean degree gaps in the ordinary\nborder map. Terminal zero pivots use exact reversible extensions. This\nmodule has no independent official-PASS claim; the parent owns integration.\nThe retained zero conjunction is the fully read ViberTeam LeanZeroTest,\nfollowing SomeJoint's earlier retained-chain construction."
from __future__ import annotations

from ..jfraction.common import km
from ..jfraction.merge_kernels import LeanZeroTest


def root_scan(b, values, denominator_tail, outcomes, *, field):
    """Phase F(alpha^j)/alpha^j iff sigma(alpha^-j)=0, preserving inputs."""
    work = b.alloc_qubits(12)
    flag = b.alloc_qubits(1)[0]
    enabled = b.alloc_bits(1)
    b.bit_store(enabled[0], False)
    zero = LeanZeroTest(b, work)
    value = values[0]
    size = len(values)
    assert len(denominator_tail) == size

    def accumulate_sigma():
        b.x(work[0])
        for word in denominator_tail:
            b.cx(word, work)

    def accumulate_value():
        for word in values[1:]:
            b.cx(word, value)

    positions = min(4095, len(outcomes))
    alpha = field.primitive_element
    for j in range(positions):
        b.bit_store(enabled[0], True, control=outcomes[j])
        b.push_condition(enabled[0])
        accumulate_sigma()
        zero.flip_if_equal(work, 0, target=flag)
        accumulate_value()
        x = field.pow(alpha, -j % 4095)
        b.gf2_imul(x, target=value, field=field)
        for bit in range(12):
            b.ccz(flag, value[bit], outcomes[j][bit])
        b.gf2_idiv(x, target=value, field=field)
        accumulate_value()
        zero.flip_if_equal(work, 0, target=flag)
        accumulate_sigma()
        b.pop_condition()
        b.bit_store(enabled[0], False)
        if j+1 < positions:
            for i, word in enumerate(denominator_tail, 1):
                b.gf2_imul(field.pow(alpha, -i % 4095), target=word, field=field)
            for i, word in enumerate(values):
                if i:
                    b.gf2_imul(field.pow(alpha, i % 4095), target=word, field=field)
    if positions > 1:
        for i, word in enumerate(denominator_tail, 1):
            b.gf2_imul(field.pow(alpha, i*(positions-1) % 4095), target=word, field=field)
        for i, word in enumerate(values):
            if i:
                b.gf2_imul(field.pow(alpha, -i*(positions-1) % 4095), target=word, field=field)
    assert zero.chain is None
    b.free(work+km.array([flag])+enabled)
