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
        from tasks.dfthcsos.checks import _chemistry_dir
        chemistry = _chemistry_dir(Path(submission_dir))
        if any((chemistry / f"angle_k_0.{suffix}").is_file() for suffix in ("kmb", "kmx")):
            from tasks.dfthcsos.circuit_checks import proxy_circuits
            return proxy_circuits(chemistry)
        return proxy_submission(Path(submission_dir))
    except Exception as exc:
        return {"status": f"FAIL: {type(exc).__name__}: {exc}"}


def g4_chemistry_floor(ctx) -> dict:
    """Require the measured 3.8× chemistry floor as well as archive improvement."""
    from ledger.gates.checks import g4_strict_improvement
    result = g4_strict_improvement(ctx)
    if result['status'] != 'PASS':
        return result
    ratio = ctx.manifest.tasks['dfthcsos'].ratio
    if ratio is None or not ratio >= 3.8:
        return {**result, 'status': f'FAIL: chemistry ratio {ratio} is below 3.8',
                'chemistry_ratio': ratio, 'chemistry_floor': 3.8}
    return {**result, 'chemistry_ratio': ratio, 'chemistry_floor': 3.8}
