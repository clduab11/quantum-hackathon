"""Gate hooks for the DQI Berlekamp–Massey generator.

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
    """Tiny-field algebra, then one reversible multiply on the simulator.

    Does not read the submission and does not build the 4,095-point circuit.
    """
    del submission_dir
    from tasks.dqi.algebra import smoke

    return smoke()


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
