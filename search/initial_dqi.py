# SPDX-License-Identifier: Apache-2.0
"""dqi seed program for the search loop (windows + generator parameters).

    python search/initial_dqi.py --out DIR

writes ``DIR/dqi.kmb`` from ``tasks.dqi.generate`` (BM/Forney on main). Later
lanes (PRA-309 confluent rebuild) swap the generator behind the same contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path


def _ensure_repo_on_path() -> None:
    candidates = [os.environ.get("QH_REPO_ROOT"), str(Path(__file__).resolve().parents[1]), os.getcwd()]
    for root in candidates:
        if root and (Path(root) / "tasks" / "dqi" / "generate.py").is_file():
            if root not in sys.path:
                sys.path.insert(0, root)
            return


_ensure_repo_on_path()

from tasks.dqi import generate as dqi_generate  # noqa: E402

# EVOLVE-BLOCK-START
NOTES = """
seed: tasks.dqi.generate Berlekamp-Massey + Forney (main). Window / STK knobs
are reserved for the evolvable block; the confluent rebuild plugs in later.
"""

GENERATOR = "bm_forney"   # bm_forney | fused | schur (later lanes)
STK_CAP = 1
# Window overrides stay None to use the committed parent windows.
BM_WINDOWS = None
PSI_WINDOWS = None


def build_circuit():
    """Return ``(kmb_bytes, report)`` for the chosen dqi generator parameters."""
    if os.environ.get("SEARCH_SMOKE") == "1":
        # Return a tiny sentinel; main() copies the package sample by path instead.
        return b"", {
            "variant": GENERATOR,
            "stk_cap": STK_CAP,
            "smoke_package_sample": True,
            "smoke_copy_from_package": True,
            "bm_windows_override": False,
            "psi_windows_override": False,
            "num_qubits": 1789,
            "static_toffoli_like": 445229,
            "num_ops": 0,
            "build_seconds": 0.0,
        }
    with tempfile.TemporaryDirectory(prefix="dqi-search-") as tmp:
        circuit, report = dqi_generate.build_decoder(Path(tmp))
        out = Path(tmp) / "dqi.kmb"
        circuit.to_file(out, format="kmb")
        data = out.read_bytes()
    report = {
        **report,
        "variant": GENERATOR,
        "stk_cap": STK_CAP,
        "bm_windows_override": BM_WINDOWS is not None,
        "psi_windows_override": PSI_WINDOWS is not None,
    }
    return data, report
# EVOLVE-BLOCK-END


def main(argv: list[str] | None = None) -> int:
    import shutil

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    data, report = build_circuit()
    target = args.out / "dqi.kmb"
    if report.get("smoke_copy_from_package"):
        data_root = Path(os.environ.get(
            "VQCC_DATA",
            "/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation",
        ))
        sample = data_root / "sample_submission" / "dqi.kmb"
        shutil.copyfile(sample, target)
    else:
        target.write_bytes(data)
    digest = hashlib.sha256()
    with target.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    payload = {
        "task": "dqi",
        "files": {"dqi.kmb": {"sha256": digest.hexdigest(), "bytes": target.stat().st_size}},
        "num_qubits": report.get("num_qubits"),
        "static_toffoli_like": report.get("static_toffoli_like"),
        "num_ops": report.get("num_ops"),
        "build_seconds": report.get("build_seconds"),
        "variant": report.get("variant"),
        "stk_cap": report.get("stk_cap"),
        "smoke_package_sample": bool(report.get("smoke_package_sample")),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
