"""Both archive entry points must reject names before Windows normalization."""
import zipfile

import pytest

from ledger.archive import UnsafeArchive, safe_extract


def test_ledger_rejects_a_raw_single_backslash(tmp_path):
    path = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('a_b', b'payload')
    path.write_bytes(path.read_bytes().replace(b'a_b', b'a\\b'))

    with pytest.raises(UnsafeArchive, match='unsafe path'):
        safe_extract(path, tmp_path / 'out')
