"""Gate hooks for the rebuilt DQI reference generator.

G2 may simulate a short shot prefix. That result is not a parity score:
parity is the full 102,400-shot verifier log.
"""

from __future__ import annotations

from pathlib import Path

# Six batches. At zero failures this is enough for eps+ < 1/16 at delta = 2^-128,
# so a correct circuit can pass the verifier's own bound. Still not full-shot parity.
SUBSAMPLE_SHOTS = 1536
SALT = "PRA171_LOCAL_PUBLIC_FIXED_SALT_0001"


def g1_smoke(submission_dir) -> dict:
    """Build a tiny RS decoder. Does not read the submission."""
    del submission_dir
    from tasks.dqi.generate import build_reference_circuit

    circuit = build_reference_circuit(7, 2, 3)
    qubits = int(circuit.num_qubits)
    toffoli = int(circuit.operation_statistics().num_toffoli_like)
    if qubits < 1 or toffoli < 1:
        return {"status": "FAIL: smoke decoder did not build", "qubits": qubits, "toffoli": toffoli}
    return {"status": "PASS", "qubits": qubits, "toffoli": toffoli}


def g2_proxy(submission_dir) -> dict:
    path = Path(submission_dir) / "dqi.kmb"
    if not path.is_file():
        return {"status": "FAIL: dqi.kmb is missing"}
    import kickmix as km
    from dqi.verify_submission_dqi import ProblemSpecDQI, verify

    circuit = km.Circuit.from_file(path)
    spec = ProblemSpecDQI.benchmark_instance(num_shots=SUBSAMPLE_SHOTS)
    try:
        summary = verify(circuit, spec, salt=SALT, max_workers=1)
    except AssertionError as exc:
        return {"status": f"FAIL: {exc}", "shots": SUBSAMPLE_SHOTS, "parity": False}
    return {
        "status": "PASS",
        "parity": False,
        "shots": SUBSAMPLE_SHOTS,
        "num_qubits": summary.get("num_qubits"),
        "toffoli_count": summary.get("toffoli_count"),
        "failures": (summary.get("value_errors") or 0) + (summary.get("phase_errors") or 0),
    }
