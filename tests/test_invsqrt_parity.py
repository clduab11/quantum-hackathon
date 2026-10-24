"""The committed invsqrt generator matches the published 92-qubit schedule."""

import hashlib
import io

from tasks.invsqrt.generate import SELECTED_KMB_SHA256, build_invsqrt_circuit, circuit_kmb_bytes
from tasks.invsqrt.mirror import run_mirror


def test_selected_circuit_matches_published_hash():
    first = circuit_kmb_bytes()
    second = circuit_kmb_bytes()
    assert first == second
    assert hashlib.sha256(first).hexdigest() == SELECTED_KMB_SHA256
    circuit = build_invsqrt_circuit()
    assert circuit.num_qubits == 92
    assert int(circuit.operation_statistics().num_toffoli_like) == 1472
    assert list(circuit.register_data) == ["x"]
    assert len(list(circuit.register_data["x"])) == 22
    buffer = io.BytesIO()
    circuit.to_file(buffer, format="kmb")
    assert buffer.getvalue() == first


def test_exhaustive_mirror_passes_every_input():
    report = run_mirror()
    assert report["pass"] is True
    assert report["tested_inputs"] == 3_133_452
    assert report["worst_ratio"] <= 1
    assert report["derivative_split"]["normalized_addresses_checked"] == 4_194_304
    assert report["min_margin_units"] > 0
