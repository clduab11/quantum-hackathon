"""Route A G1/G2 hooks for the reference invsqrt circuit (PRA-226).

Independent of the held dataset-derived implementation. G2 simulates a short
input prefix of the submitted circuit; it is not parity. G3 proves full shots.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import replace
from pathlib import Path

import kickmix as km

from tasks.invsqrt.reference import build_nr_circuit

REFERENCE_SHA256 = "e2bf8eb64350a4460a271fc7f1d591ef125b1e276377e9a0f64b96ab3ca321e1"
SUBSAMPLE_SHOTS = 1536
SALT = "PRA171_LOCAL_PUBLIC_FIXED_SALT_0001"


def g1_smoke(submission_dir: Path) -> dict:
    """Require pinned reference bytes and the single 22-qubit register x."""
    path = Path(submission_dir) / "invsqrt.kmb"
    if not path.is_file():
        return {"status": "FAIL: invsqrt.kmb is missing"}
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    expected = io.BytesIO()
    build_nr_circuit(10).to_file(expected, format="kmb")
    if data != expected.getvalue() or digest != REFERENCE_SHA256:
        return {"status": "FAIL: invsqrt.kmb is not the pinned reference output", "sha256": digest}
    circuit = km.Circuit.from_file(str(path))
    registers = circuit.register_data
    if list(registers) != ["x"] or len(list(registers["x"])) != 22:
        return {"status": f"FAIL: register schema {list(registers)}"}
    return {
        "status": "PASS",
        "sha256": digest,
        "num_qubits": circuit.num_qubits,
        "static_toffoli": int(circuit.operation_statistics().num_toffoli_like),
    }


def g2_proxy(submission_dir: Path) -> dict:
    """Simulate x=1..1536, once each, with the package verifier; not parity."""
    smoke = g1_smoke(submission_dir)
    if smoke["status"] != "PASS":
        return smoke
    from invsqrt.verify_submission_invsqrt import ProblemSpecInvSqrt, verify

    circuit = km.Circuit.from_file(str(Path(submission_dir) / "invsqrt.kmb"))
    spec = replace(ProblemSpecInvSqrt.for_n_p(10), max_x=SUBSAMPLE_SHOTS, shots_per_x=1)
    try:
        summary = verify(circuit, spec, salt=SALT, max_workers=1)
    except AssertionError as exc:
        return {"status": f"FAIL: {exc}", "shots": SUBSAMPLE_SHOTS, "parity": False}
    return {
        "status": summary["status"],
        "parity": False,
        "scope": "not parity: x=1..1536, one shot per input",
        "shots": summary["verified_shots"],
        "failures": 0,  # The verifier raises on the first restoration or phase failure.
        "sha256": summary["circuit_sha256"],
        "num_qubits": summary["num_qubits"],
        "toffoli_count": summary["toffoli_count"],
        "worst_error_over_tolerance": summary["worst_error_over_tolerance"],
    }
