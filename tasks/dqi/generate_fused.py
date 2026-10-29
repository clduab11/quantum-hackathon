# SPDX-License-Identifier: Apache-2.0
# Source port; not independent clean-room authorship. See fused/PROVENANCE.md.
"""Build SomeJoint's fused DQI decoder from committed source; write only OUT/dqi.kmb.

The vendored files under fused/source/ are byte-identical to the notebook's
embedded source. Their imports rely on the author's sys.path layout, so the
unchanged build.py runs as a script in its own interpreter, the way its author
runs it. Every vendored file is checked against SOURCE_MAP.json first. No
notebook, circuit, data file or network access is an input.

PRA-322: optional hengck23 edit patches are applied only onto a scratch copy of
the vendored tree (see fused/patches/). Vendored bytes and SOURCE_MAP.json stay
true.
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
BUILD_REL = Path('exp/decoder/build.py')


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


def stage_source(scratch: Path, *, apply_hengck23: bool) -> list[dict]:
    """Copy vendored source into scratch; optionally apply the edit layer."""
    staged = scratch / 'source'
    shutil.copytree(PORT / 'source', staged, symlinks=False)
    receipts = []
    if apply_hengck23:
        from tasks.dqi.fused.patches import apply_patches
        receipts = apply_patches(staged)
    return receipts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--hengck23-edits', action='store_true',
                        help='Apply fused/patches (hengck23 edit layer) on a scratch copy.')
    args = parser.parse_args()
    started = time.monotonic()
    pinned = check_pins()
    with tempfile.TemporaryDirectory(prefix='dqi-fused-') as scratch_name:
        scratch = Path(scratch_name)
        receipts = stage_source(scratch, apply_hengck23=args.hengck23_edits)
        built = scratch / 'dqi.kmb'
        build = scratch / 'source' / BUILD_REL
        # -B keeps __pycache__ out of the source tree; build.py also writes dqi.build.json,
        # which stays in scratch so OUT holds only the circuit.
        subprocess.run([sys.executable, '-B', str(build), str(built)], cwd=scratch, check=True,
                       stdout=sys.stderr)
        record = json.loads(built.with_suffix('.build.json').read_text())
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / 'dqi.kmb'
        shutil.move(built, path)
    digest = sha256(path)
    print(json.dumps(dict(variant='fused-confluent' + ('+hengck23' if args.hengck23_edits else ''),
                          pinned_files=pinned, patches=receipts,
                          num_qubits=record['Q'],
                          static_toffoli_like=record['T_static'], num_ops=record['num_ops'],
                          num_bits=record['num_bits'], build_seconds=time.monotonic() - started,
                          sha256=digest, bytes=path.stat().st_size, stages=record['stages']),
                     indent=2), flush=True)


if __name__ == '__main__':
    main()
