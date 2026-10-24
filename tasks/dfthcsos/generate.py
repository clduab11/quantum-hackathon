# SPDX-License-Identifier: Apache-2.0
# ANGLE circuit builder ported from the competition package
# verifiers/dfthcsos/example_submission/angle_k_reference_circuit.py
# (Apache-2.0). Praxen wrapper: --out writes dfthcsos/angle_k_*.kmb and
# copies the packaged reference factorization.
#
# The public 1.44× factor (Signed-Digit Memory v3, NPZ SHA-256
# c5b4165e7b1dcacf1d287746642414a9ba6086b4279e5ede2bb73e21e6aebd98)
# is not used. That notebook is Apache-2.0, but it copies the factor
# from an earlier archive and states that the starting chemistry factors
# originate with k256.dev, whose generator and licence are not available.
# R10 forbids shipping that file. This generator rebuilds the package
# reference (score target 1.0), not the 1.44× lineage.

"""Write the reference dfthcsos submission from the packaged factorization.

The factorization bytes are the competition package's sample ``submission.npz``
(Apache-2.0), checked by SHA-256 and copied. The ANGLE circuits are rebuilt
here from its ``angle_words`` with the packaged ordinary-QROM construction
(``b_rot`` 12, ``J`` 8). ``.kmb`` files are never committed.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
from collections.abc import Sequence
from math import ceil
from operator import index
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

DEFAULT_DATA = Path(
    os.environ.get(
        "VQCC_DATA",
        "/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation",
    )
)
REFERENCE_NPZ_SHA256 = "14d5cc25eb3bf82a9ccb87c811db28d127bef6d28697dd190dc1e875de3bfe69"
REFERENCE_B_ROT = 12
REFERENCE_BATCH = 8
# Packaged sample circuits. A match means this builder reproduced them.
REFERENCE_ANGLE_SHA256 = {
    0: "7bfb3983accc6ff97d6ab41a88deae924f1d1c97cf30e60879d0bff5688a8e25",
    1: "a04b6d0d57ce851b123af265066aaab2ab33353ea049d26acd534727466d72b6",
    2: "5c1b8987bc3fa1a4b8607e470f8c8f1392c22e7a7dbcb228f0ce9ec986e18058",
    3: "16ac67cdcaf3e2c6abdd98c4138ff1ae8a56cfc4ae15622bcdb3d3a3ba1e22cf",
    4: "d21cdd4c7e94196654aab15ebcabfe10ce8d343151a5e8dc3672e76684b6628d",
    5: "63b8d4cba36955e6098321f3b2ef3e34401dd276fa629b2e490d043b1743880b",
    6: "5bf740428e661d035fda860142578f421969e35e0df2e4e024fbf01a7340b378",
    7: "606009582111a22bd549b795c8d115ac8bbeb124bc8da24a80380eca6d34163d",
    8: "57c7cc51f5922fff6e95d76e1f723d4c2d029a241da643b95684d6322157a8fe",
    9: "22cbe2828988ff954fc07fd971a25e6bc04a02c302bf2cc642e4c3535daaad65",
}

SELECTION_REGISTER = "selection"


def word_register(j: int) -> str:
    return f"word_{j}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def batch_deltas(angle_words: npt.ArrayLike, batch_size: int) -> npt.NDArray[np.int64]:
    """``(K, N+R*B, J)`` tables. ``delta[0] = batch[0]`` and later batches are XORs."""
    words = np.asarray(angle_words)
    if words.ndim != 2 or not np.issubdtype(words.dtype, np.integer):
        raise ValueError("angle_words must be a 2-D integer array (N + R*B, N - 1)")
    if np.any(words < 0):
        raise ValueError("angle_words must be non-negative")
    batch_size = index(batch_size)
    if batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    num_vectors, num_angles = words.shape
    num_batches = max(1, ceil(num_angles / batch_size))
    padded = np.zeros((num_vectors, num_batches * batch_size), dtype=np.int64)
    padded[:, :num_angles] = words
    batches = padded.reshape(num_vectors, num_batches, batch_size).transpose(1, 0, 2)
    deltas = batches.copy()
    deltas[1:] ^= batches[:-1]
    return deltas


def build_angle_k_circuit(delta: npt.ArrayLike, brot: int):
    """Ordinary QROM for one ``(A, J)`` XOR-difference table."""
    import kickmix as km

    delta = np.asarray(delta, dtype=np.int64)
    brot = index(brot)
    if not 1 <= brot <= 63:
        raise ValueError("brot must be an integer between 1 and 63")
    if delta.ndim != 2 or delta.shape[0] < 2:
        raise ValueError("delta must have shape (A, J) with A >= 2 addresses")
    if np.any(delta < 0) or np.any(delta >= np.int64(1) << brot):
        raise ValueError(f"words must lie in [0, 2**{brot})")
    num_rows, batch_size = delta.shape
    num_bits = (num_rows - 1).bit_length()
    builder = km.CircuitBuilder()
    selection = builder.create_quantum_register(num_bits, SELECTION_REGISTER)
    words = [builder.create_quantum_register(brot, word_register(j)) for j in range(batch_size)]
    ancillas = builder.alloc_qubits(num_bits - 1) if num_bits > 1 else []
    bits = [selection[i] for i in reversed(range(num_bits))]

    def load(row: int, control: Any) -> None:
        for j in range(batch_size):
            for bit in reversed(range(brot)):
                if (int(delta[row, j]) >> bit) & 1:
                    builder.cx(control, words[j][bit])

    def node(control: Any, level: int, lo: int, hi: int) -> None:
        if lo >= num_rows:
            return
        if hi <= num_rows and (hi - lo == 1 or np.all(delta[lo:hi] == delta[lo, 0])):
            load(lo, control)
            return
        mid = (lo + hi) // 2
        if num_rows <= mid:
            node(control, level + 1, lo, mid)
            return
        bit, ancilla = bits[level], ancillas[level - 1]
        builder.x(bit)
        builder.init_and(control, bit, ancilla)
        builder.x(bit)
        node(ancilla, level + 1, lo, mid)
        builder.cx(control, ancilla)
        node(ancilla, level + 1, mid, hi)
        builder.del_and(control, bit, ancilla)

    half = 1 << (num_bits - 1)
    builder.x(bits[0])
    node(bits[0], 1, 0, half)
    builder.x(bits[0])
    node(bits[0], 1, half, 2 * half)
    return builder.finish_circuit()


def build_angle_k_family(angle_words: npt.ArrayLike, brot: int, batch_size: int):
    return tuple(build_angle_k_circuit(delta, brot) for delta in batch_deltas(angle_words, batch_size))


def load_angle_words(path: Path) -> npt.NDArray[np.int64]:
    loaded: Any = np.load(path, allow_pickle=False)
    with loaded as archive:
        if "angle_words" not in archive.files:
            raise KeyError(f"{path} has no angle_words entry")
        words = np.array(archive["angle_words"])
    if words.ndim != 2 or not np.issubdtype(words.dtype, np.integer):
        raise ValueError(f"{path}: angle_words must be a 2-D integer array")
    return words.astype(np.int64)


def reference_npz(data: Path) -> Path:
    path = data / "sample_submission" / "dfthcsos" / "submission.npz"
    if not path.is_file():
        raise FileNotFoundError(f"packaged reference factorization is missing: {path}")
    digest = sha256_file(path)
    if digest != REFERENCE_NPZ_SHA256:
        raise ValueError(f"reference submission.npz SHA-256 is {digest}, expected {REFERENCE_NPZ_SHA256}")
    return path


def write_family(circuits: Sequence[Any], directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for k, circuit in enumerate(circuits):
        path = directory / f"angle_k_{k}.kmb"
        circuit.to_file(path, format="kmb")
        paths.append(path)
    return paths


def generate(out: Path, data: Path = DEFAULT_DATA) -> dict[str, str]:
    """Write ``<out>/dfthcsos/`` and return relative path → SHA-256."""
    source = reference_npz(data)
    destination = out / "dfthcsos"
    destination.mkdir(parents=True, exist_ok=True)
    npz_path = destination / "submission.npz"
    shutil.copyfile(source, npz_path)
    circuits = build_angle_k_family(load_angle_words(npz_path), REFERENCE_B_ROT, REFERENCE_BATCH)
    files = {"dfthcsos/submission.npz": sha256_file(npz_path)}
    for k, path in enumerate(write_family(circuits, destination)):
        digest = sha256_file(path)
        files[f"dfthcsos/{path.name}"] = digest
        expected = REFERENCE_ANGLE_SHA256.get(k)
        mark = "match" if digest == expected else "DIFFERS"
        print(f"{path.name}: sha256 {digest} ({mark})")
    print(f"submission.npz: sha256 {files['dfthcsos/submission.npz']}")
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Submission root. Receives dfthcsos/.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="Competition package root (VQCC_DATA).")
    args = parser.parse_args()
    generate(args.out, args.data)


if __name__ == "__main__":
    main()
