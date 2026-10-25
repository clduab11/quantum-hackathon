"""The invsqrt generator is deterministic. The circuit is a port. The coefficient calibration has unresolved rights."""

import hashlib
import io

from tasks.invsqrt.fit_coefficients import EXPECTED_ROW_SHA256, derived_tables, row_sha256, coefficient_rows
from tasks.invsqrt.generate import (
    SELECTED_KMB_SHA256,
    build_invsqrt_circuit,
    circuit_kmb_bytes,
    compilation_report,
)
from tasks.invsqrt.mirror import run_mirror


def test_coefficients_come_from_the_fit():
    _cfg, tables, _worst, report = derived_tables()
    assert row_sha256(coefficient_rows(tables)) == EXPECTED_ROW_SHA256
    assert report["worst_ratio"] < 1
    assert "21136269" not in str(report)


def test_selected_circuit_is_deterministic():
    first = circuit_kmb_bytes()
    second = circuit_kmb_bytes()
    assert first == second
    assert hashlib.sha256(first).hexdigest() == SELECTED_KMB_SHA256
    circuit = build_invsqrt_circuit()
    assert circuit.num_qubits == 90
    assert int(circuit.operation_statistics().num_toffoli_like) == 1448
    assert int(circuit.operation_statistics().num_z_pow(min_clifford_hierarchy_level=4)) == 44
    assert list(circuit.register_data) == ["x"]
    assert len(list(circuit.register_data["x"])) == 22
    buffer = io.BytesIO()
    circuit.to_file(buffer, format="kmb")
    assert buffer.getvalue() == first
    built = compilation_report()
    assert built["coefficient_provenance"] == "regenerated; dataset-adapted calibration; licence unresolved"
    assert built["circuit_authorship"] == "port"
    assert built["phase"]["phase_match"] is True
    assert built["calibration"]["margin_units"] > 0
    assert built["final"]["expected_toffoli"] == 1437.5
    assert built["estimate"]["ratio"] > 13.07


def test_exhaustive_mirror_passes_every_input():
    report = run_mirror()
    assert report["pass"] is True
    assert report["tested_inputs"] == 3_133_452
    assert report["worst_ratio"] <= 1
    assert report["derivative_split"]["normalized_addresses_checked"] == 4_194_304
    assert report["min_margin_units"] > 0
    assert report["phase_match"] is True
    assert report["calibration_margin_units"] > 0
    assert report["rotations"] == 44
    assert report["qubits"] == 90
