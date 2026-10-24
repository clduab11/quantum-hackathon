"""Bind calibration to the committed reference bytes, independent of its location."""
import hashlib
from pathlib import Path

import yaml

MANIFEST = Path(__file__).resolve().parents[1] / 'ledger/p0-4-artifacts.yaml'


def expected_reference():
    rows = yaml.safe_load(MANIFEST.read_text())['reference_files']
    return {str(Path(row['path']).relative_to('sample_submission')):
            {'bytes': row['bytes'], 'sha256': row['sha256']} for row in rows}


def reference_identity(root):
    root = Path(root)
    expected = expected_reference()
    files = {p.relative_to(root).as_posix(): p for p in root.rglob('*') if not p.is_dir()}
    if set(files) != set(expected):
        raise ValueError('Reference file set differs from committed reference_files manifest.')
    for name, path in files.items():
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f'Reference must contain regular contained files: {name}')
        with path.open('rb') as stream:
            actual = {'bytes': path.stat().st_size,
                      'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}
        if actual != expected[name]:
            raise ValueError(f'Reference content differs from committed manifest: {name}')
    return expected
