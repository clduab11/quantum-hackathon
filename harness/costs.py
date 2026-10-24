"""Small accounting checks; acceptance remains the supplied verifiers' decision."""
import math


def effective_lambda(normalization, gap):
    if not (math.isfinite(normalization) and math.isfinite(gap) and 0 < gap < 2 * normalization):
        raise ValueError('Expected finite Lambda and 0 < E_gap < 2 Lambda.')
    return math.sqrt(gap * (2 * normalization - gap))


def invsqrt_cost(qubits, toffolis, total_t):
    return qubits * (toffolis + total_t / 4)


def dqi_cost(qubits, toffolis, repetition):
    return repetition * qubits**2 * toffolis


def dfthcsos_cost(qubits, toffolis, lambda_eff):
    return lambda_eff * toffolis * qubits
