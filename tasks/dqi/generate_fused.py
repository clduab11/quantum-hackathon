# SPDX-License-Identifier: Apache-2.0
# Source port; not independent clean-room authorship. See fused/PROVENANCE.md.
"""Build SomeJoint's fused DQI decoder from committed source; write only OUT/dqi.kmb.

The vendored files under fused/source/ are byte-identical to the notebook's
embedded source. Their imports rely on the author's sys.path layout, so the
unchanged build.py runs as a script in its own interpreter, the way its author
runs it. Every vendored file is checked against SOURCE_MAP.json first. No
notebook, circuit, data file or network access is an input.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

PORT = Path(__file__).resolve().parent / 'fused'
BUILD = PORT / 'source/exp/decoder/build.py'


def sha256(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_pins():
    """Fail before building if any vendored file differs from its pin."""
    files = json.loads((PORT / 'SOURCE_MAP.json').read_text())['files']
    drift = [item['file'] for item in files if sha256(PORT / item['file']) != item['port_sha256']]
    if drift:
        raise SystemExit(f'vendored source differs from SOURCE_MAP.json: {drift}')
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    pinned = check_pins()
    with tempfile.TemporaryDirectory(prefix='dqi-fused-') as scratch:
        built = Path(scratch) / 'dqi.kmb'
        # -B keeps __pycache__ out of the source tree; build.py also writes dqi.build.json,
        # which stays in scratch so OUT holds only the circuit.
        subprocess.run([sys.executable, '-B', str(BUILD), str(built)], cwd=scratch, check=True,
                       stdout=sys.stderr)
        record = json.loads(built.with_suffix('.build.json').read_text())
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / 'dqi.kmb'
        shutil.move(built, path)
    digest = sha256(path)
    print(json.dumps(dict(variant='fused-confluent', pinned_files=pinned, num_qubits=record['Q'],
                          static_toffoli_like=record['T_static'], num_ops=record['num_ops'],
                          num_bits=record['num_bits'], build_seconds=time.monotonic() - started,
                          sha256=digest, bytes=path.stat().st_size, stages=record['stages']),
                     indent=2), flush=True)


if __name__ == '__main__':
    main()
