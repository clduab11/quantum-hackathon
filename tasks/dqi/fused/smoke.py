# SPDX-License-Identifier: Apache-2.0
"""Complete-domain checks of the vendored GF(2^12) multiplier and inverse.

Run as a script: it uses the author's sys.path layout (the decoder directory,
whose common.py adds the source root and exp/arithmetic), so the vendored bare
module names never enter the caller's interpreter. Prints one JSON report.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'source/exp/decoder'))

import numpy as np  # noqa: E402
import kickmix as km  # noqa: E402
from common import read, write  # noqa: E402
import field as ar  # noqa: E402  (exp/arithmetic/field.py, via common.py)

GF = km.GF2Field(12)
X = np.arange(4096, dtype=np.uint64)
# Fixed, input-independent companions; no seed selection.
Y = (X * 73 + 11) % 4096
Z = X ^ 0xA5B


def run(circuit, inputs):
    sim = km.Simulator(batch_size=len(X), seed=293)
    for reg, values in inputs:
        write(sim, reg, values)
    sim.do(circuit)
    return sim


def clean(sim, circuit, used):
    used = {str(q) for reg in used for q in reg}
    rest = [km.q(i) for i in range(circuit.num_qubits) if str(km.q(i)) not in used]
    return not rest or not sim.read_across_shots(km.array(rest)).any()


def check_mul_xor():
    b = km.CircuitBuilder()
    x, y, z = (b.alloc_qubits(12) for _ in range(3))
    ar.mul_xor(b, x, y, z)
    c = b.finish_circuit()
    sim = run(c, [(x, X), (y, Y), (z, Z)])
    expected = Z ^ np.array([GF.mul(int(a), int(v)) for a, v in zip(X, Y)], dtype=np.uint64)
    assert np.array_equal(read(sim, x), X) and np.array_equal(read(sim, y), Y), 'mul_xor changed inputs'
    assert np.array_equal(read(sim, z), expected), 'mul_xor product mismatch'
    assert not sim.read_phase_flipped_across_shots().any(), 'mul_xor phase'
    assert clean(sim, c, [x, y, z]), 'mul_xor scratch not clean'
    return c.operation_statistics().num_toffoli_like


def check_inverse():
    b = km.CircuitBuilder()
    x = b.alloc_qubits(12)
    target = ar.inverse(b, x)
    c = b.finish_circuit()
    sim = run(c, [(x, X)])
    expected = np.array([GF.invert(int(a)) if a else 0 for a in X], dtype=np.uint64)
    assert np.array_equal(read(sim, x), X), 'inverse changed its input'
    assert np.array_equal(read(sim, target), expected), 'inverse mismatch (0 must map to 0)'
    assert not sim.read_phase_flipped_across_shots().any(), 'inverse phase'
    assert clean(sim, c, [x, target]), 'inverse scratch not clean'
    return c.operation_statistics().num_toffoli_like


if __name__ == '__main__':
    print(json.dumps(dict(status='PASS', domain=len(X), mul_xor_toffolis=check_mul_xor(),
                          inverse_toffolis=check_inverse())))
