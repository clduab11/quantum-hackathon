# SPDX-License-Identifier: Apache-2.0
# Source port; not independent clean-room authorship. See hankel/PROVENANCE.md.
"""Build submission-9 DQI from committed Python source; write only OUT/dqi.kmb."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tasks.dqi.hankel.decoder import build_decoder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    circuit, stages = build_decoder()
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / 'dqi.kmb'
    circuit.to_file(path, format='kmb')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    print(json.dumps(dict(variant='hankel-cyclic-gold', num_qubits=circuit.num_qubits,
                         static_toffoli_like=circuit.operation_statistics().num_toffoli_like,
                         num_ops=len(circuit), num_bits=circuit.num_bits,
                         build_seconds=time.monotonic() - started, sha256=digest,
                         bytes=path.stat().st_size, stages=stages), indent=2), flush=True)


if __name__ == '__main__':
    main()
