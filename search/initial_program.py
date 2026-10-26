# SPDX-License-Identifier: Apache-2.0
"""dfthcsos ANGLE_k family builder for the OpenEvolve search loop (see search/README.md).

Fixed contract (everything outside the EVOLVE block; OpenEvolve reverts edits made there):

    python initial_program.py --out DIR --factorization FILE.npz --source-brot 12

reads ``angle_words`` from the declared factor file, calls ``build_family`` and writes
``DIR/dfthcsos/angle_k_{k}.kmb`` plus ``DIR/dfthcsos/submission.npz``. The NPZ is a byte copy of the
factor file when the circuits load the source precision; otherwise it holds the same arrays with
``angle_words`` requantised to the circuits' precision, exactly as tasks/dfthcsos/circuit.py does.
A JSON report goes to stdout. Nothing here depends on a seed, a salt or a verifier outcome.

The seed reproduces Google's packaged reference family: ordinary QROM, b_rot 12, J 8, ten circuits,
cost 3,355,599,588.3155365 (ratio 1.0).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
from pathlib import Path

import numpy as np


def _ensure_repo_on_path() -> None:
    """The evolved copy of this file lives in a temp dir; make `tasks` importable anyway."""
    candidates = [os.environ.get("QH_REPO_ROOT"), str(Path(__file__).resolve().parents[1]), os.getcwd()]
    for root in candidates:
        if root and (Path(root) / "tasks" / "dfthcsos" / "generate.py").is_file():
            if root not in sys.path:
                sys.path.insert(0, root)
            return


_ensure_repo_on_path()

from tasks.dfthcsos.generate import (  # noqa: E402
    batch_deltas, build_angle_k_circuit, load_angle_words, write_family,
)
from tasks.dfthcsos.qrom import build_qrom, mobius, quantize_words  # noqa: E402,F401

QUBIT_CAP = 128      # verifier cap on every ANGLE_k circuit
NUM_ANGLES = 75      # N - 1 Givens angles per vector (FeMoCo76o113e, N = 76)
# Rows = N + R*B; Google's packaged factor has 76 + 65*60 = 3976, so its selection register has 12 qubits.
# The wrapper reads the row count from the factor file, so a declared factor with another (R, B) also works.

# EVOLVE-BLOCK-START
NOTES = """
seed: Google's reference layout. Ordinary unary-iteration QROM (build_angle_k_circuit), BROT 12,
BATCH_SIZE 8 -> 10 circuits of 119 qubits; verifier T_total 93,237, Q_total 730, ratio 1.0.
Append one line per change: what changed, the hypothesis, and what the evaluator said.
"""

BROT = 12        # bits per angle word the circuits load; 12 = source precision (NPZ stays a byte copy)
BATCH_SIZE = 8   # J words per circuit -> ceil(75 / J) circuits; each needs at least 12 + J*BROT qubits


def build_family(words: np.ndarray, source_brot: int):
    """Return ``(circuits, report)`` for the ``(rows, 75)`` integer table ``words`` at ``source_brot`` bits.

    Circuit k maps |a>|z> to |a>|z XOR delta_k(a)> with delta_0 = batch_0 and delta_k = batch_k ^ batch_{k-1}
    (batch_deltas returns exactly these), so after circuits 0..k the word registers hold batch k; it must
    leave the selection register, every ancilla and the global phase exactly as it found them.
    Optionally return ``(circuits, report, table)`` where ``table`` is the integer word table the circuits
    actually load (at the circuits' precision): the wrapper then writes that table as ``angle_words``, which
    keeps the static proxy honest if you quantise differently from quantize_words.
    Alternatives already in the repository: tasks.dfthcsos.qrom.build_qrom(delta, brot, bank_bits=0|1|2,
    scratch=k, pebble_degree=d) builds an exact ANF/banked XOR oracle (returns (circuit, stats)).
    """
    table = quantize_words(words, source_brot, BROT)
    circuits = [build_angle_k_circuit(delta, BROT) for delta in batch_deltas(table, BATCH_SIZE)]
    report = {"variant": "ordinary-qrom", "brot": BROT, "batch_size": BATCH_SIZE}
    return circuits, report
# EVOLVE-BLOCK-END


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _stat(stats, name: str) -> int:
    """kickmix exposes some OperationStatistics counters as attributes and some as methods."""
    value = getattr(stats, name)
    return int(value() if callable(value) else value)


def family_layout(circuits) -> tuple[int, int]:
    """``(brot, batch_size)`` read from the public registers of the first circuit, as the verifier does."""
    registers = circuits[0].register_data
    words = sorted(name for name in registers if name.startswith("word_"))
    if "selection" not in registers or not words:
        raise ValueError("circuits must declare a 'selection' register and word_0..word_{J-1} registers")
    widths = {len(registers[name]) for name in words}
    if len(widths) != 1:
        raise ValueError(f"word registers differ in width: {sorted(widths)}")
    return widths.pop(), len(words)


def _jsonable(value):
    """Keep the report JSON-safe whatever the evolved block puts in it (numpy scalars, arrays, paths)."""
    if hasattr(value, "item") and not isinstance(value, (list, tuple, dict)):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if hasattr(value, "tolist"):
        return value.tolist()
    return str(value)


def generate(out: Path, factorization: Path, source_brot: int) -> dict:
    words = load_angle_words(factorization)
    if words.ndim != 2 or words.shape[1] != NUM_ANGLES or words.shape[0] < 2:
        raise ValueError(f"angle_words has shape {words.shape}, expected (rows, {NUM_ANGLES})")
    rows = int(words.shape[0])
    selection_bits = (rows - 1).bit_length()
    built = build_family(words, source_brot)
    if len(built) == 3:
        circuits, report, loaded = built
        loaded = np.asarray(loaded)
    else:
        circuits, report = built
        loaded = None
    circuits = list(circuits)
    if not circuits:
        raise ValueError("build_family returned no circuits")
    brot, batch_size = family_layout(circuits)
    if len(circuits[0].register_data["selection"]) != selection_bits:
        raise ValueError(f"the selection register needs {selection_bits} qubits for {rows} vectors, "
                         f"got {len(circuits[0].register_data['selection'])}")
    expected = math.ceil(NUM_ANGLES / batch_size)
    if len(circuits) != expected:
        raise ValueError(f"J={batch_size} needs {expected} circuits for {NUM_ANGLES} angles, got {len(circuits)}")
    if loaded is None:
        loaded = quantize_words(words, source_brot, brot)
    if loaded.shape != words.shape or not np.issubdtype(loaded.dtype, np.integer):
        raise ValueError("the loaded word table must be an integer array with the shape of angle_words")
    if np.any(loaded < 0) or np.any(loaded >= (1 << brot)):
        raise ValueError(f"loaded words must lie in [0, 2**{brot})")
    per_circuit = []
    for k, circuit in enumerate(circuits):
        qubits = int(circuit.num_qubits)
        if qubits > QUBIT_CAP:
            raise ValueError(f"angle_k_{k} uses {qubits} qubits > {QUBIT_CAP}")
        stats = circuit.operation_statistics()
        per_circuit.append({"k": k, "num_qubits": qubits,
                            "toffoli_like_static": int(_stat(stats, "num_toffoli_like")),
                            "z_pow": int(_stat(stats, "num_z_pow")), "num_instructions": len(circuit)})
    destination = Path(out) / "dfthcsos"
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("output dfthcsos directory must be empty; use a fresh build directory")
    destination.mkdir(parents=True, exist_ok=True)
    npz = destination / "submission.npz"
    byte_copy = brot == source_brot and np.array_equal(loaded, words)
    if byte_copy:
        shutil.copyfile(factorization, npz)
    else:
        with np.load(factorization, allow_pickle=False) as data:
            arrays = {key: data[key] for key in data.files}
        arrays["angle_words"] = loaded.astype(np.int64)
        np.savez(npz, **arrays)
    paths = [npz, *write_family(circuits, destination)]
    report = json.loads(json.dumps(dict(report), default=_jsonable))
    return {
        **report, "brot": brot, "batch_size": batch_size, "num_circuits": len(circuits), "rows": rows,
        "max_qubits": max(c["num_qubits"] for c in per_circuit),
        "toffoli_like_static_total": sum(c["toffoli_like_static"] for c in per_circuit),
        "circuits": per_circuit, "factorization_sha256": sha256_file(factorization),
        "npz_is_byte_copy": byte_copy,
        "files": {str(p.relative_to(out)): {"sha256": sha256_file(p), "size": p.stat().st_size} for p in paths},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--factorization", type=Path, required=True)
    parser.add_argument("--source-brot", type=int, default=12)
    args = parser.parse_args()
    print(json.dumps(generate(args.out, args.factorization, args.source_brot), indent=1, default=_jsonable))


if __name__ == "__main__":
    main()
