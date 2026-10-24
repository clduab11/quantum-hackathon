"""Contain ZIP extraction in a scratch directory; never extract links or aliases."""
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import stat
import tempfile
import zipfile


@contextmanager
def unpack(archive):
    with tempfile.TemporaryDirectory(prefix='vqcc-g0-') as temp:
        root = Path(temp)
        with zipfile.ZipFile(archive) as z:
            seen = set()
            for member in z.infolist():
                path = PurePosixPath(member.filename)
                mode = stat.S_IFMT(member.external_attr >> 16)
                if (not path.parts or path.is_absolute() or '..' in path.parts
                        or '\\' in member.filename or str(path) in seen
                        or mode not in (0, stat.S_IFREG, stat.S_IFDIR)):
                    raise ValueError(f'Unsafe or duplicate ZIP path: {member.filename!r}')
                seen.add(str(path))
            z.extractall(root)
        yield root
