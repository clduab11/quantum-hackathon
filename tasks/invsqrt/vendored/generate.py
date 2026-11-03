# SPDX-License-Identifier: Apache-2.0
"""Stage the unchanged licensed circuit. This is vendoring, not circuit generation.

Use --fetch once to download the single version-pinned member anonymously.
Rebuilds use only the hash-pinned file beneath VQCC_DATA, without network access.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import urllib.request
import zipfile

PIN = json.loads(Path(__file__).with_name('SOURCE.json').read_text())
SHA256 = PIN['sha256']
INPUT_PATH = PIN['path']


def checked_bytes(source: Path) -> bytes:
    data = Path(source).read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != SHA256:
        raise ValueError(f'SHA-256 {actual} does not match accepted invsqrt {SHA256}')
    return data


def fetch(destination: Path) -> None:
    """Fetch only the accepted member; reject unexpected archive contents."""
    destination = Path(destination)
    if destination.exists():
        checked_bytes(destination)
        return
    with urllib.request.urlopen(PIN['download_url'], timeout=120) as response:
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError('single-member download exceeds size limit')
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if (len(members) != 1 or members[0].filename not in
                    ('invsqrt.kmb', 'circuits/invsqrt.kmb') or
                    members[0].file_size != PIN['size_bytes']):
                raise ValueError('download is not the selected single invsqrt member')
            data = archive.read(members[0])
    if len(data) != PIN['size_bytes'] or hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('download size or SHA-256 differs from the accepted source')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(data)


def stage(source: Path, out: Path) -> dict:
    data = checked_bytes(source)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'invsqrt.kmb').write_bytes(data)
    return {'file': 'invsqrt.kmb', 'sha256': SHA256, 'size_bytes': len(data)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--data', type=Path, default=Path(os.environ.get(
        'VQCC_DATA', '/home/cld-main/work/vqcc-data')))
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    source = args.data / INPUT_PATH
    if args.fetch:
        fetch(source)
    print(json.dumps(stage(source, args.out), sort_keys=True))


if __name__ == '__main__':
    main()
