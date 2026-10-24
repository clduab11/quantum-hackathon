# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Praxen / Chris Dukes.

"""Exact checks for the DQI field and a tiny Berlekamp–Massey decoder.

The competition syndrome is ``s_i = sum_j e_j * alpha^{(i+1) j}`` with
``alpha = 2``. These checks do not build the 4,095-point circuit.
"""

from __future__ import annotations

import kickmix as km

from tasks.dqi.bm_forney.gu_classical import GF2n

COMPETITION_MODULUS = 4179
TINY_POLY = 0x13  # x^4 + x + 1, GF(16), primitive element 2.


def competition_field() -> km.GF2Field:
    field = km.GF2Field(12)
    if field.modulus != COMPETITION_MODULUS:
        raise RuntimeError(f"modulus {field.modulus} is not {COMPETITION_MODULUS}")
    if field.primitive_element != 2:
        raise RuntimeError(f"primitive element {field.primitive_element} is not 2")
    return field


def syndromes(errors: list[int], n_syndromes: int, field: GF2n) -> list[int]:
    """Competition syndrome, ``alpha = field.gen``."""
    alpha = field.gen
    out = []
    for i in range(n_syndromes):
        acc = 0
        for position, value in enumerate(errors):
            if value:
                acc ^= field.mul(value, field.pow(alpha, (i + 1) * position))
        out.append(acc)
    return out


def _poly_trim(coeffs: list[int]) -> list[int]:
    out = list(coeffs)
    while len(out) > 1 and out[-1] == 0:
        out.pop()
    return out


def _poly_add(a: list[int], b: list[int]) -> list[int]:
    n = max(len(a), len(b))
    return _poly_trim([(a[i] if i < len(a) else 0) ^ (b[i] if i < len(b) else 0) for i in range(n)])


def _poly_scale(a: list[int], factor: int, field: GF2n) -> list[int]:
    return _poly_trim([field.mul(c, factor) for c in a])


def _poly_mul(a: list[int], b: list[int], field: GF2n) -> list[int]:
    out = [0] * (len(a) + len(b) - 1)
    for i, av in enumerate(a):
        if not av:
            continue
        for j, bv in enumerate(b):
            if bv:
                out[i + j] ^= field.mul(av, bv)
    return _poly_trim(out)


def berlekamp_massey(syndrome: list[int], field: GF2n) -> list[int]:
    """Locator ``C``, ``C[0] == 1``, for a characteristic-2 syndrome.

    ``syndrome[n]`` is the standard ``S_{n+1}``. The loop is the
    Berlekamp–Massey iteration in Lin and Costello: one discrepancy,
    then either a length update or a correction by ``x^m B``.
    """
    connection = [1]
    backup = [1]
    length = 0
    shift = 1
    scale = 1
    for n, symbol in enumerate(syndrome):
        discrepancy = symbol
        for i in range(1, length + 1):
            if i < len(connection):
                discrepancy ^= field.mul(connection[i], syndrome[n - i])
        if discrepancy == 0:
            shift += 1
            continue
        term = _poly_mul([0] * shift + [1], backup, field)
        term = _poly_scale(term, field.mul(discrepancy, field.inv(scale)), field)
        next_connection = _poly_add(connection, term)
        if 2 * length <= n:
            backup = connection
            connection = next_connection
            length = n + 1 - length
            scale = discrepancy
            shift = 1
        else:
            connection = next_connection
            shift += 1
    return connection


def chien_forney(connection: list[int], syndrome: list[int], n_points: int, field: GF2n) -> list[int]:
    """Error word from a monic-constant locator. Empty locator means no error."""
    if connection == [1]:
        return [0] * n_points
    # Key equation: locator(x) * S(x) = omega(x) mod x^{n}, deg omega < deg locator.
    # S has no leading 1. S[0] is the first competition syndrome.
    omega = _poly_mul(connection, syndrome, field)
    omega = omega[: len(connection) - 1]
    derivative = [0] * max(len(connection) - 1, 1)
    for i in range(1, len(connection)):
        if i % 2 == 1:
            derivative[i - 1] = connection[i]
    derivative = _poly_trim(derivative) if any(derivative) else [0]
    errors = [0] * n_points
    for position in range(n_points):
        x = field.pow(field.gen, position)
        if x == 0 or _eval(connection, field.inv(x), field) != 0:
            continue
        numer = _eval(omega, field.inv(x), field)
        denom = _eval(derivative, field.inv(x), field)
        errors[position] = field.mul(numer, field.inv(denom))
    return errors


def _eval(coeffs: list[int], x: int, field: GF2n) -> int:
    acc = 0
    power = 1
    for coeff in coeffs:
        if coeff:
            acc ^= field.mul(coeff, power)
        power = field.mul(power, x)
    return acc


def _tiny_cases() -> None:
    field = GF2n(4, TINY_POLY)
    if field.gen != 2:
        raise RuntimeError("GF(16) primitive element is not 2")
    length = 15
    syndromes_n = 6
    cases = [
        [0] * length,
        _one(length, 0, 1),
        _one(length, 7, 9),
        _two(length, 1, 3, 4, 11),
        _two(length, 2, 14, 5, 6),
    ]
    for errors in cases:
        syndrome = syndromes(errors, syndromes_n, field)
        locator = berlekamp_massey(syndrome, field)
        got = chien_forney(locator, syndrome, length, field)
        if got != errors:
            raise RuntimeError(f"tiny decode mismatch: {errors} -> {got}")


def _one(length: int, position: int, value: int) -> list[int]:
    errors = [0] * length
    errors[position] = value
    return errors


def _two(length: int, p0: int, v0: int, p1: int, v1: int) -> list[int]:
    errors = [0] * length
    errors[p0] = v0
    errors[p1] = v1
    return errors


def _simulator_multiply() -> dict:
    """One reversible GF(2^12) product, checked on the kickmix simulator."""
    gf = competition_field()
    left_value, right_value = 13, 21
    builder = km.CircuitBuilder()
    left = builder.create_quantum_register(12, name="A")
    right = builder.create_quantum_register(12, name="C")
    product = builder.create_quantum_register(12, name="T")
    for i in range(12):
        if (left_value >> i) & 1:
            builder.x(left[i])
        if (right_value >> i) & 1:
            builder.x(right[i])
    builder.init_gf2_mul(km.array(left), km.array(right), target=km.array(product), field=gf)
    circuit = builder.finish_circuit()
    simulator = km.Simulator(batch_size=1, debug_print=False, counting_operations=True, seed=1)
    simulator.use_same_registers_as(circuit)
    simulator.do(circuit)

    def read(register) -> int:
        bits = simulator.read_across_shots(km.array(register))
        return sum(int(bits[i, 0]) << i for i in range(12))

    field = GF2n(12, COMPETITION_MODULUS)
    expect = field.mul(left_value, right_value)
    got = read(product)
    if read(left) != left_value or read(right) != right_value or got != expect:
        raise RuntimeError(f"simulator product {got} != {expect}")
    toffoli = int(circuit.operation_statistics().num_toffoli_like)
    if toffoli < 1:
        raise RuntimeError("the product primitive emitted no Toffoli-like gate")
    return {"qubits": int(circuit.num_qubits), "toffoli": toffoli, "product": got}


def smoke() -> dict:
    """G1 body: field identity, tiny exact decode, one simulator primitive."""
    try:
        field = competition_field()
        model = GF2n(12, field.modulus)
        if model.gen != 2:
            raise RuntimeError(f"GF2n primitive element is {model.gen}")
        for value in (1, 2, 19, 4095):
            if model.mul(value, model.inv(value)) != 1:
                raise RuntimeError(f"inverse failed for {value}")
        errors = [0] * 8
        errors[3] = 5
        got = syndromes(errors, 4, model)
        expect = [model.mul(5, model.pow(2, (i + 1) * 3)) for i in range(4)]
        if got != expect:
            raise RuntimeError("single-error syndrome formula drifted")
        _tiny_cases()
        primitive = _simulator_multiply()
    except Exception as exc:
        return {"status": f"FAIL: {exc}"}
    return {"status": "PASS", "modulus": field.modulus, "primitive_element": 2, **primitive}
