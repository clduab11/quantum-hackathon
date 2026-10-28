# SPDX-License-Identifier: Apache-2.0
"""invsqrt seed program for the search loop (schedule + coefficient knobs).

    python search/initial_invsqrt.py --out DIR

writes ``DIR/invsqrt.kmb`` from ``tasks.invsqrt.generate``. Only the EVOLVE block
is editable; the wrapper and output contract are fixed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


def _ensure_repo_on_path() -> None:
    candidates = [os.environ.get("QH_REPO_ROOT"), str(Path(__file__).resolve().parents[1]), os.getcwd()]
    for root in candidates:
        if root and (Path(root) / "tasks" / "invsqrt" / "generate.py").is_file():
            if root not in sys.path:
                sys.path.insert(0, root)
            return


_ensure_repo_on_path()

from tasks.invsqrt import generate as invsqrt_generate  # noqa: E402

# EVOLVE-BLOCK-START
NOTES = """
seed: tasks.invsqrt.generate selected schedule (PRA-200 lineage). Knobs below
select among committed schedule / coefficient paths; append one line per change.
"""

# Schedule / coefficient knobs the later staged-63 lane (PRA-310 sibling) will extend.
SCHEDULE = "selected"          # selected | public_port | schedule90
COEFFICIENT_SOURCE = "fitted"  # fitted | mirror tables from generate


def build_circuit():
    """Return ``(kmb_bytes, report)`` for the chosen schedule/coefficient pair."""
    if os.environ.get("SEARCH_SMOKE") == "1":
        # Smoke keeps stages 0/1/3 under a minute: ship the package sample and
        # read resources from kickmix. Full generator rebuild stays on the loop path.
        data_root = Path(os.environ.get(
            "VQCC_DATA",
            "/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation",
        ))
        sample = data_root / "sample_submission" / "invsqrt.kmb"
        data = sample.read_bytes()
        import kickmix as km
        circuit = km.Circuit.from_file(str(sample))
        stats = circuit.operation_statistics()
        toffoli = int(stats.num_toffoli_like)
        return data, {
            "variant": SCHEDULE,
            "coefficient_source": COEFFICIENT_SOURCE,
            "smoke_package_sample": True,
            "qubits": int(circuit.num_qubits),
            "static_toffoli": toffoli,
            "expected_toffoli": toffoli,
            "rotations": int(stats.num_z_pow(min_clifford_hierarchy_level=4)),
            "margin_units": 1.0,
            "sha256": hashlib.sha256(data).hexdigest(),
            "estimated_ratio": 1.0,
            "cost_c": float(toffoli),
        }
    report = invsqrt_generate.compilation_report()
    estimate = report["estimate"]
    cost_c = float(estimate.get("cost") or estimate.get("toffoli_equivalents")
                   or report["final"]["expected_toffoli"])
    return invsqrt_generate.circuit_kmb_bytes(), {
        "variant": SCHEDULE,
        "coefficient_source": COEFFICIENT_SOURCE,
        "qubits": report["final"]["qubits"],
        "static_toffoli": report["final"]["static_toffoli"],
        "expected_toffoli": report["final"]["expected_toffoli"],
        "rotations": report["final"]["rotations"],
        "margin_units": report["calibration"]["margin_units"],
        "sha256": report["sha256"],
        "estimated_ratio": report["estimate"]["ratio"],
        "cost_c": cost_c,
    }
# EVOLVE-BLOCK-END


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    data, report = build_circuit()
    target = args.out / "invsqrt.kmb"
    target.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    payload = {
        "task": "invsqrt",
        "files": {"invsqrt.kmb": {"sha256": digest, "bytes": len(data)}},
        **report,
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
