# SPDX-License-Identifier: Apache-2.0
# Port driver for the Berlekamp-Massey + Forney decoder. This is a port,
# not independent clean-room authorship. Parents, used paths, licences
# and file hashes are in tasks/dqi/PROVENANCE.md and NOTICE.
# Gu et al., andigu/uncompute, commit 64b5a13aa249f1360846657392e6c66817b26d0f.
# No .kmb file and no .npz file is an input. No copyright year is added.

"""Berlekamp–Massey + Forney decoder for the competition DQI instance.

``python tasks/dqi/generate.py --out DIR`` writes ``DIR/dqi.kmb`` and nothing
else. The instance is fixed: RS(4095, 4025, 71), 70 syndrome registers
``S0``..``S69``, classical record ``E0``..``E4094``.

Each run regenerates the multiplication formulas and the tower inverse
chain on the shipped ``GF(2^12)`` (modulus 4179, primitive element 2).
Truncation windows are the parent's measured windows. The fixed SHA-256
mask is not applied: the sweep kicks the phase from the per-shot record.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

_PORT = Path(__file__).resolve().parent / "bm_forney"

# Replacements that keep the V6 sweep visible to the symbolic builder.
# The sweep body calls kickmix field ops directly. The symbolic builder
# must forget those outputs, or a later uncompute will treat them as
# still-known forms.
_SWEEP_EDITS = (
    ("b.physical[q]", "b.wire(q)"),
    ("b.physical[root]", "b.wire(root)"),
    ("b.physical[loc[0]]", "b.wire(loc[0])"),
    ("b.physical[ps[h]]", "b.wire(ps[h])"),
    (
        "raw.cx(arr([q for word in words for q in word]),arr([q for _ in words for q in target]))",
        "raw.cx(arr([q for word in words for q in word]),arr([q for _ in words for q in target]));b.invalidate(target)",
    ),
    ("tr=A.open('tree',11);", "b.invalidate(val);tr=A.open('tree',11);"),
    (
        "raw.del_and(b.wire(root),arr(om),arr(loc))",
        "raw.del_and(b.wire(root),arr(om),arr(loc));b.forms[loc[0]]=S.ZERO",
    ),
    (
        "raw.init_and(b.wire(root),arr(om),arr(loc))",
        "raw.init_and(b.wire(root),arr(om),arr(loc));b.invalidate(loc)",
    ),
    (
        "raw.cx(arr([w[k] for w in omw]),arr(om*len(omw)))",
        "raw.cx(arr([w[k] for w in omw]),arr(om*len(omw)));b.invalidate(om)",
    ),
)


def _port_modules():
    """Import the port from its directory once. Later calls reuse it."""
    port = str(_PORT)
    if port not in sys.path:
        sys.path.insert(0, port)
    import gu_formula_derivation as formulas

    return formulas


def regenerate_tables(work: Path) -> dict:
    """Regenerate field formulas for modulus 4179 and merge the windows.

    The returned object is what ``gu_port`` reads. Multiplication tables
    and ``LIN`` come from this process. ``bm_windows`` and ``psi_windows``
    come from the committed parent windows, not from a numeric target file.
    """
    formulas = _port_modules()
    tables, timing = formulas.run_b12()
    if not formulas.certify_kt(tables["KT12"], formulas.FIELD):
        raise RuntimeError("KT12 does not multiply GF(2^12) modulus 4179")
    if formulas.FIELD.gen != 2:
        raise RuntimeError(f"derived primitive element is {formulas.FIELD.gen}, expected 2")
    windows = json.loads((_PORT / "windows.json").read_text())
    constants = dict(windows)
    constants.update(tables)
    path = work / "constants.json"
    path.write_text(json.dumps(constants, sort_keys=True))
    os.environ["DQI_CONSTANTS"] = str(path)
    os.environ["DQI_BORROW"] = "affine"
    return {"timings": timing, "modulus": formulas.CONTRACT["gf_poly"], "primitive": formulas.FIELD.gen}


def _install_sweep(port, symbolic):
    """Point the sweep at the streamed Chien/Forney body."""
    source = (_PORT / "round2_gadgets.py").read_text()
    marker = "def lean_sweep("
    start = source.index(marker)
    body = source[start:]
    for old, new in _SWEEP_EDITS:
        if old not in body:
            raise RuntimeError(f"sweep edit missed its target: {old[:60]}")
        body = body.replace(old, new)
    namespace = {"S": symbolic}
    exec(body, namespace)

    def native_sweep(builder, emitter, alloc, omw, ebw, abw):
        qubits = [q for register in omw + ebw + abw for q in register]
        builder.suspended = True
        namespace["stream_sweep"](builder, emitter, alloc, omw, ebw, abw)
        builder.invalidate(qubits)
        builder.suspended = False

    port.emit_sweep = native_sweep


def build_decoder(work: Path):
    """Build the competition decoder. ``work`` holds regenerated constants."""
    report = regenerate_tables(work)
    import borrow as borrow_route
    import gu_port as port
    import round2_gadgets as gadgets
    import symbolic_runtime as symbolic

    port = importlib.reload(port)
    gadgets = importlib.reload(gadgets)
    port.Builder = symbolic.SymbolicBuilder
    port.declare_registers = symbolic.declare_registers
    port.borrow_template = borrow_route.borrow_template
    gadgets.install(port, top_first=True, pebble_last=True, norm_pebble=True, compact_from=70)
    _install_sweep(port, symbolic)
    started = time.monotonic()
    builder, counted = port.build()
    builder.k.free(builder.measurement)
    circuit = builder.k.finish_circuit()
    report.update(
        build_seconds=time.monotonic() - started,
        counted_toffoli_like=int(counted),
        num_qubits=int(circuit.num_qubits),
        static_toffoli_like=int(circuit.operation_statistics().num_toffoli_like),
        num_ops=len(circuit),
        num_bits=int(circuit.num_bits),
    )
    return circuit, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Directory that receives dqi.kmb.")
    parser.add_argument("--format", choices=("kmb",), default="kmb")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    output = args.out / "dqi.kmb"
    with tempfile.TemporaryDirectory(prefix="dqi-bm-") as tmp:
        circuit, report = build_decoder(Path(tmp))
        circuit.to_file(output, format=args.format)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(
        f"Wrote {output}: Q {report['num_qubits']}, "
        f"static Toffoli-like {report['static_toffoli_like']}, "
        f"ops {report['num_ops']}, build {report['build_seconds']:.1f}s."
    )
    print(f"sha256 {digest}")
    print("field", report["modulus"], "primitive", report["primitive"])


if __name__ == "__main__":
    main()
