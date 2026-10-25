# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Praxen / Chris Dukes.
"""Classical-mask projection by Lagrange interpolation.

Method: Manwithacat's public 70-position syndrome-span projection. New code
from the mathematical specification; not a copy or transliteration of the
parent projection module. The author has read that module, so this is not a
strict clean room. See PROVENANCE.md and D-PRA236-01.

For x_j = alpha**j, interpolate L(x) = sum_i lambda_i*x**(i+1) so
Tr(L(x_j)*e_j) equals the input bit-mask parity at the first n positions.
Interpolate L(x)/x using Lagrange cardinal polynomials. This avoids a field
matrix inverse. The trace Gram matrix converts between field and bit masks.
"""
from functools import cache

import kickmix as km


class ProjectionPlan:
    def __init__(self, field, count):
        self.field = field
        self.degree = field.degree
        self.count = count
        self.order = (1 << self.degree) - 1
        if not 1 <= count <= self.order:
            raise ValueError('Projection count must lie within the nonzero field points.')
        self.trace_columns = tuple(self.parity_mask(1 << i) for i in range(self.degree))
        # Invert the binary trace map with bit-packed row elimination.
        rows = [sum(((c >> row) & 1) << col for col, c in enumerate(self.trace_columns))
                | (1 << (self.degree + row)) for row in range(self.degree)]
        for col in range(self.degree):
            pivot = next(row for row in range(col, self.degree) if rows[row] >> col & 1)
            rows[col], rows[pivot] = rows[pivot], rows[col]
            for row in range(self.degree):
                if row != col and rows[row] >> col & 1:
                    rows[row] ^= rows[col]
        self.dual = tuple(sum(((row >> (self.degree + col)) & 1) << i
                              for i, row in enumerate(rows)) for col in range(self.degree))
        nodes = [field.pow(field.primitive_element, j) for j in range(count)]
        cardinal = []
        for j, node in enumerate(nodes):
            polynomial = [1]
            denominator = node
            for k, other in enumerate(nodes):
                if k == j:
                    continue
                product = [0] * (len(polynomial) + 1)
                for i, coefficient in enumerate(polynomial):
                    product[i] ^= field.mul(other, coefficient)
                    product[i + 1] ^= coefficient
                polynomial = product
                denominator = field.mul(denominator, node ^ other)
            cardinal.append(tuple(field.div(c, denominator) for c in polynomial))
        self.cardinal = tuple(cardinal)

    def trace(self, value):
        total = 0
        for _ in range(self.degree):
            total ^= value
            value = self.field.square(value)
        return total

    @cache
    def parity_mask(self, value):
        return sum(self.trace(self.field.mul(value, 1 << bit)) << bit
                   for bit in range(self.degree))

    def coefficients(self, masks):
        if len(masks) != self.count:
            raise ValueError('One input mask is required per interpolation point.')
        result = [0] * self.count
        for mask, column in zip(masks, self.cardinal):
            value = 0
            for bit, dual in enumerate(self.dual):
                if mask >> bit & 1:
                    value ^= dual
            for i, weight in enumerate(column):
                result[i] ^= self.field.mul(weight, value)
        return result

    def residual(self, masks):
        if not self.count <= len(masks) <= self.order:
            raise ValueError('Outcome count is outside the projection domain.')
        coefficients = self.coefficients(masks[:self.count])
        output = []
        for j, mask in enumerate(masks):
            x = self.field.pow(self.field.primitive_element, j)
            value = 0
            for coefficient in reversed(coefficients):
                value = self.field.mul(value ^ coefficient, x)
            output.append(mask ^ self.parity_mask(value))
        return output


@cache
def competition_plan():
    field = km.GF2Field(12)
    if (field.modulus, field.primitive_element) != (4179, 2):
        raise ValueError('Unexpected DQI field.')
    return ProjectionPlan(field, 70)


def dual_basis():
    """Compatibility boundary for ViberTeam's trace-tensor phase routine."""
    return competition_plan().dual


def _linear_xor(builder, source, destination, images):
    for bit, image in enumerate(images):
        while image:
            lowest = image & -image
            builder.cx(source[bit], destination[lowest.bit_length() - 1])
            image ^= lowest


def project_masks(builder, syndromes, outcomes, *, field=None):
    """Emit the syndrome phase and return residual masks, preserving inputs."""
    field = km.GF2Field(12) if field is None else field
    count, degree = len(syndromes), field.degree
    plan = competition_plan() if (degree, count, field.modulus) == (12, 70, 4179) else ProjectionPlan(field, count)
    if not count <= len(outcomes) <= plan.order or any(len(w) != degree for w in (*syndromes, *outcomes)):
        raise ValueError('Projection register dimensions do not match the field.')
    coefficients = [builder.alloc_bits(degree) for _ in range(count)]
    for register in coefficients:
        builder.bit_store(register, False)
    for j, polynomial in enumerate(plan.cardinal):
        for i, weight in enumerate(polynomial):
            _linear_xor(builder, outcomes[j], coefficients[i],
                        [field.mul(weight, dual) for dual in plan.dual])
    for word, coefficient in zip(syndromes, coefficients):
        for bit, image in enumerate(plan.trace_columns):
            for other in range(degree):
                if image >> other & 1:
                    builder.cz(coefficient[bit], word[other])
    residual = []
    for j, original in enumerate(outcomes):
        register = builder.alloc_bits(degree)
        builder.bit_store(register, False)
        if j >= count:
            builder.cx(original, register)
            x = field.pow(field.primitive_element, j)
            weight = x
            for coefficient in coefficients:
                _linear_xor(builder, coefficient, register,
                            [plan.parity_mask(field.mul(weight, 1 << bit)) for bit in range(degree)])
                weight = field.mul(weight, x)
        residual.append(register)
    for register in coefficients:
        builder.free(register)
    return residual
