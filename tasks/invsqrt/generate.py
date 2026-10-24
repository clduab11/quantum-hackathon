"""Kickmix generator for the invsqrt task.

Parent (Apache-2.0): Quantum Circuits | Signed-Digit Memory, v3,
Artem1410 (anazemcev),
https://www.kaggle.com/code/anazemcev/quantum-circuits-signed-digit-memory
Source snapshot SHA-256:
79f6373302cb916a88f65a1b142024d4d2d0b14e41eb58bef3152ebd45ffd0ca

The circuit phases |x> by 1/sqrt(x) for x in 1..3,133,452. It uses the
parent's selected schedule: quadratic signed-digit Horner, a 256-entry QROM,
and no Newton iteration. The same commit writes a byte-identical invsqrt.kmb.

    python tasks/invsqrt/generate.py --out DIR
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tasks.invsqrt import signed_digit as sd  # noqa: E402

# Selected public schedule (Cfg in the parent notebook).
F2 = 8          # fractional bits of the quadratic coefficient
F1 = 19         # fractional bits of the linear coefficient
FYR = 27        # fractional bits of the raw phase word before the dropped low bit
GY = 1          # low bits of the phase word that are computed and then dropped
DROP2 = (5,)    # signed-digit rows omitted from the quadratic Horner stage
QROM_ENTRIES = 256
WIDTH = 22
MAX_X = 3_133_452
BETA = 1
PARENT_URL = "https://www.kaggle.com/code/anazemcev/quantum-circuits-signed-digit-memory"
PARENT_LICENCE = "Apache-2.0"
PARENT_SNAPSHOT_SHA256 = "79f6373302cb916a88f65a1b142024d4d2d0b14e41eb58bef3152ebd45ffd0ca"
# Published selected-circuit hash from the parent notebook (v3).
SELECTED_KMB_SHA256 = "63f70e623dd995f4f87ca13254f46f991a5ae545d4c20c80e8510f5ff0a49bbd"

assert (sd.F2, sd.F1, sd.FYR, sd.GY, sd.DROP2) == (F2, F1, FYR, GY, DROP2)


def build_invsqrt_circuit():
    """Build the selected kickmix circuit. Deterministic."""
    cfg, tables, _worst = sd.load_or_build_tables()
    return sd.build_selected(cfg, tables, sd.layout(cfg, tables))


def circuit_kmb_bytes() -> bytes:
    """Canonical .kmb bytes of the selected circuit."""
    buffer = io.BytesIO()
    build_invsqrt_circuit().to_file(buffer, format="kmb")
    return buffer.getvalue()


def write_invsqrt(out_dir: Path) -> Path:
    """Write `invsqrt.kmb` into `out_dir` and return its path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "invsqrt.kmb"
    data = circuit_kmb_bytes()
    target.write_bytes(data)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Directory for invsqrt.kmb.")
    args = parser.parse_args(argv)
    target = write_invsqrt(args.out)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f"{target} sha256={digest} bytes={target.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
