"""PRA-284 G1/G2 hooks for the regenerated Gluzdov v7 port.

G1 binds the submitted bytes to the selected port and checks its register.
G2 simulates a short prefix, not parity; G3 performs the full verification.
G5 independently refits on CUDA and rebuilds from the committed generator.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import kickmix as km

PORT_SHA256 = "17fc223d79d3f1f15ef448389072209972b373403dd0a45352f4fe7eaff541ad"
SUBSAMPLE_SHOTS = 1536
SALT = "PRA171_LOCAL_PUBLIC_FIXED_SALT_0001"


def g1_smoke(submission_dir: Path) -> dict:
    """Require pinned public-port bytes and the single 22-qubit register x."""
    path = Path(submission_dir) / "invsqrt.kmb"
    if not path.is_file():
        return {"status": "FAIL: invsqrt.kmb is missing"}
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != PORT_SHA256:
        return {"status": "FAIL: invsqrt.kmb is not the pinned public-port output", "sha256": digest}
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
