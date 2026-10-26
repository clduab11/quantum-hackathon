# SPDX-License-Identifier: Apache-2.0
# Port of SomeJoint v7; see PROVENANCE.md and SOURCE_MAP.json.
# Praxen: package imports; production functions only; no notebook runtime.
'Recursive LDU field scaler: trade one-time gates for an eleven-bit peak.\n\nTop GF4096 is split over GF64; GF64 diagonal scales are themselves LDU\nmaps over GF8. Only GF8 leaves use a full product temporary. Interior\nscalars are proved nonzero, so only the top level needs a zero extension.\nThe ten-intermediate zero test is the existing credited lean-AND method.'
from __future__ import annotations

from contextlib import contextmanager


def xor_zero(b, source, target):
    """XOR the exact zero predicate using n-2 clean AND intermediates."""
    n = len(source)
    assert n >= 3
    b.x(source)
    chain = b.alloc_qubits(n - 2)
    b.init_and(source[0], source[1], chain[0])
    for i in range(1, n - 2):
        b.init_and(chain[i-1], source[i+1], chain[i])
    b.ccx(chain[-1], source[-1], target)
    for i in reversed(range(1, n - 2)):
        b.del_and(chain[i-1], source[i+1], chain[i])
    b.del_and(source[0], source[1], chain[0])
    b.free(chain)
    b.x(source)


@contextmanager
def gamma_coordinates(b, ratio, delta, field):
    """Expose 1+r+delta*r² in h bits plus one retained kernel coordinate."""
    from ..jfraction.tower import elimination_gates
    h = len(ratio)
    kernel = field.invert(delta)
    kernel_bit = (kernel & -kernel).bit_length() - 1
    columns = [(1 << i) ^ field.mul(delta, field.square(1 << i))
               ^ ((i == kernel_bit) << h) for i in range(h)]
    gates = None
    for extra_position in range(h):
        try:
            gates = elimination_gates(columns + [1 << extra_position])
            break
        except StopIteration:
            continue
    assert gates is not None
    extra = b.alloc_qubits(1)
    wires = ratio + extra
    for gate, i, j in reversed(gates):
        getattr(b, gate)(wires[i], wires[j])
    b.x(ratio[0])
    try:
        yield ratio
    finally:
        b.x(ratio[0])
        for gate, i, j in gates:
            getattr(b, gate)(wires[i], wires[j])
        b.free(extra)


def theta_chart(b, low, high, control, basis, *, inverse):
    from ..jfraction.tower import elimination_gates
    h = len(low)
    gates = elimination_gates([basis.inner.mul(basis.delta, 1 << i) for i in range(h)])

    def constant(reverse):
        for gate, i, j in gates if reverse else reversed(gates):
            if gate == "cx":
                b.ccx(control, low[i], low[j])
            else:
                assert gate == "swap"
                b.cswap(control, low[i], low[j])

    if inverse:
        constant(True)
        b.cswap(control, low, high)
        b.ccx(control, high, low)
    else:
        b.ccx(control, high, low)
        b.cswap(control, low, high)
        constant(False)


def leaf_scale(b, scalar, words, *, divide, field):
    """Nonzero GF8 scaler, six scratch bits, one inverse shared by words."""
    assert len(scalar) == 3
    inverse, scaffold = b.init_gf2_inverse_with_scaffold(scalar, field=field)
    assert len(scaffold) == 0
    temporary = b.alloc_qubits(3)
    factor, undo = (inverse, scalar) if divide else (scalar, inverse)
    for word in words:
        b.ixor_gf2_mul(word, factor, target=temporary, field=field)
        b.swap(word, temporary)
        b.del_gf2_mul(word, undo, target=temporary, field=field)
    b.free(temporary)
    b.del_gf2_inverse_with_scaffold(scalar, target=inverse, scaffold=scaffold, field=field)
    b.free(inverse)


def _ldu(b, scalar, words, *, divide, known_nonzero):
    n = len(scalar)
    assert n in (6, 12) and all(len(word) == n for word in words)
    basis, h = b.bases[n], n // 2
    inner = basis.inner
    zero = None
    if not known_nonzero:
        zero = b.alloc_qubits(1)[0]
        xor_zero(b, scalar, zero)
        b.cx(zero, scalar[0])
    for word in [scalar, *words]:
        basis.change_basis(b, word, to_tower=True)
    a, ratio = scalar[:h], scalar[h:]
    chart = b.alloc_qubits(1)[0]
    xor_zero(b, a, chart)
    b.cswap(chart, a, ratio)
    halves = [(word[:h], word[h:]) for word in words]
    for low, high in halves:
        theta_chart(b, low, high, chart, basis, inverse=divide)

    def scale(factor, targets, inverse):
        if h == 3:
            leaf_scale(b, factor, targets, divide=inverse, field=inner)
        else:
            _ldu(b, factor, targets, divide=inverse, known_nonzero=True)

    def upper():
        b.gf2_imul(basis.delta, target=ratio, field=inner)
        for low, high in halves:
            b.ixor_gf2_mul(ratio, high, target=low, field=inner)
        b.gf2_idiv(basis.delta, target=ratio, field=inner)

    def lower():
        for low, high in halves:
            b.ixor_gf2_mul(ratio, low, target=high, field=inner)

    # Six smaller-scale lifetimes, each returning its factor unchanged.
    scale(a, [ratio], True)
    if divide:
        lower()
    else:
        upper()
        scale(a, [low for low, _ in halves], False)
    with gamma_coordinates(b, ratio, basis.delta, inner) as gamma:
        scale(gamma, [a], False)
        scale(a, [high for _, high in halves], divide)
        scale(gamma, [a], True)
    if divide:
        scale(a, [low for low, _ in halves], True)
        upper()
    else:
        lower()
    scale(a, [ratio], False)

    b.cswap(chart, a, ratio)
    xor_zero(b, a, chart)
    b.free(chart)
    for word in reversed([scalar, *words]):
        basis.change_basis(b, word, to_tower=False)
    if zero is not None:
        b.cx(zero, scalar[0])
        xor_zero(b, scalar, zero)
        b.free(zero)


def scale_words(b, scalar, words, *, divide=False):
    assert len(scalar) == 12
    _ldu(b, scalar, words, divide=divide, known_nonzero=False)
