# SPDX-License-Identifier: Apache-2.0
"""PRA-232 deterministic circuit-half builder; factor arrays are never refitted.

Run as ``python -m tasks.dfthcsos.circuit --out DIR``. Use --factorization
and --source-brot for a different declared factor input (PRA-201).
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np

from tasks.dfthcsos.generate import (
    DEFAULT_DATA, batch_deltas, load_angle_words, reference_npz, sha256_file, write_family,
)
from tasks.dfthcsos.qrom import build_qrom, quantize_words


def generate(out, *, factorization=None, source_brot=12, brot=12, batch_size=9,
             bank_bits=0, scratch=8, pebble_degree=4):
    source = reference_npz(DEFAULT_DATA) if factorization is None else Path(factorization)
    words = quantize_words(load_angle_words(source), source_brot, brot)
    # Validate/build every circuit before creating output files. A failed layout
    # must not leave a partially updated family that looks ready to verify.
    built = [build_qrom(d, brot, bank_bits=bank_bits, scratch=scratch,
                        pebble_degree=pebble_degree) for d in batch_deltas(words, batch_size)]
    destination = Path(out) / 'dfthcsos'
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('output dfthcsos directory must be empty; use a fresh build directory')
    destination.mkdir(parents=True, exist_ok=True)
    npz = destination / 'submission.npz'
    if source_brot == brot:
        shutil.copyfile(source, npz)
    else:
        with np.load(source, allow_pickle=False) as data:
            arrays = {k: data[k] for k in data.files}
        arrays['angle_words'] = words
        # numpy.savez uses fixed ZIP timestamps; byte identity is tested separately.
        np.savez(npz, **arrays)
    paths = [npz, *write_family([c for c, _ in built], destination)]
    return dict(factorization_sha256=sha256_file(source), source_brot=source_brot,
                brot=brot, batch_size=batch_size, bank_bits=bank_bits, scratch=scratch,
                pebble_degree=pebble_degree, circuits=[r for _, r in built],
                files={str(p.relative_to(out)): dict(sha256=sha256_file(p), size=p.stat().st_size)
                       for p in paths})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--factorization', type=Path)
    p.add_argument('--source-brot', type=int, default=12)
    p.add_argument('--b-rot', type=int, default=12)
    p.add_argument('--batch-size', type=int, default=9)
    p.add_argument('--bank-bits', type=int, choices=[0, 1, 2], default=0)
    p.add_argument('--scratch', type=int, default=8)
    p.add_argument('--pebble-degree', type=int, default=4)
    a = p.parse_args()
    print(json.dumps(generate(a.out, factorization=a.factorization, source_brot=a.source_brot,
                              brot=a.b_rot, batch_size=a.batch_size, bank_bits=a.bank_bits,
                              scratch=a.scratch, pebble_degree=a.pebble_degree), indent=2))


if __name__ == '__main__':
    main()
