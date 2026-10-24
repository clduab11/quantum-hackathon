"""Gate hooks for the dfthcsos generator. G1 is a tiny circuit. G2 does not simulate."""

from __future__ import annotations

from pathlib import Path

from tasks.dfthcsos.checks import proxy_submission
from tasks.dfthcsos.generate import build_angle_k_circuit


def g1_smoke(submission_dir) -> dict:
    """Build a 2-address QROM. Ignores the submission; this is a builder smoke test."""
    del submission_dir
    import numpy as np

    circuit = build_angle_k_circuit(np.array([[1, 0], [0, 3]], dtype=np.int64), 4)
    qubits = int(circuit.num_qubits)
    if qubits < 1:
        return {"status": "FAIL: smoke circuit has no qubits"}
    return {"status": "PASS", "qubits": qubits}


def g2_proxy(submission_dir) -> dict:
    try:
        return proxy_submission(Path(submission_dir))
    except Exception as exc:
        return {"status": f"FAIL: {type(exc).__name__}: {exc}"}
