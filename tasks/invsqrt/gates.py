"""Ledger G1 and G2 hooks for the invsqrt generator."""

from __future__ import annotations

import hashlib
from pathlib import Path

import kickmix as km

from tasks.invsqrt.generate import SELECTED_KMB_SHA256, circuit_kmb_bytes
from tasks.invsqrt.mirror import run_mirror


def _invsqrt_path(submission_dir: Path) -> Path:
    hits = [
        path for path in Path(submission_dir).rglob("invsqrt.*")
        if path.is_file() and path.suffix in {".kmb", ".kmx"} and "__MACOSX" not in path.parts
    ]
    if len(hits) != 1:
        raise ValueError(f"expected one invsqrt circuit, found {len(hits)}")
    return hits[0]


def g1_smoke(submission_dir: Path) -> dict:
    """The submitted circuit is the generator's .kmb and exposes one 22-qubit register x."""
    path = _invsqrt_path(submission_dir)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    expected = circuit_kmb_bytes()
    if data != expected or digest != SELECTED_KMB_SHA256:
        return {
            "status": "FAIL: invsqrt.kmb is not the selected generator output",
            "sha256": digest,
        }
    circuit = km.Circuit.from_file(str(path))
    registers = list(circuit.register_data)
    if registers != ["x"] or len(list(circuit.register_data["x"])) != 22:
        return {"status": f"FAIL: register schema {registers}"}
    stats = circuit.operation_statistics()
    return {
        "status": "PASS",
        "sha256": digest,
        "num_qubits": circuit.num_qubits,
        "static_toffoli": int(stats.num_toffoli_like),
    }


def g2_proxy(submission_dir: Path) -> dict:
    """Exhaustive integer mirror. The file check keeps the proof attached to this circuit."""
    smoke = g1_smoke(submission_dir)
    if smoke.get("status") != "PASS":
        return smoke
    report = run_mirror()
    if not report["pass"]:
        return {"status": f"FAIL: mirror {report}", **report}
    return {"status": "PASS", **report, "sha256": smoke["sha256"]}
