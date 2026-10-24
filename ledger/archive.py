"""Submission zips: safe extraction and deterministic builds.

`safe_extract` applies the archive checks from the PRA-171 inventory (§4) before anything reads
the files: no duplicate paths, no absolute or `..` paths, no backslashes, no links or special
files.

`build_zip` writes a byte-reproducible zip (sorted entries, fixed timestamps and permissions), so
G5 can compare the SHA-256 of a rebuilt zip with the one in the manifest. Every candidate zip is
built with it.
"""

from __future__ import annotations

import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)
FILE_MODE = 0o644


class UnsafeArchive(ValueError):
    """The zip contains a path or entry type that is not allowed."""


def check_members(archive: zipfile.ZipFile) -> None:
    members = archive.infolist()
    # Compare normalised paths: "a/b", "./a/b", "a//b" and "a/b/" all extract to the same place.
    names = [PurePosixPath(m.filename).as_posix() for m in members]
    if len(set(names)) != len(names):
        raise UnsafeArchive("zip has duplicate paths")
    for member in members:
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts or "\\" in member.filename:
            raise UnsafeArchive(f"zip has an unsafe path: {member.filename!r}")
        mode = member.external_attr >> 16
        if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise UnsafeArchive(f"zip contains a link or special file: {member.filename!r}")


def safe_extract(zip_path: Path, dest: Path) -> Path:
    """Check every member, then extract into `dest` (which must not exist yet)."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(zip_path) as archive:
        check_members(archive)
        archive.extractall(dest)
    return dest


def build_zip(src_dir: Path, dest_zip: Path) -> Path:
    """Zip every regular file under `src_dir` deterministically."""
    src_dir = Path(src_dir)
    files = sorted(p for p in src_dir.rglob("*") if p.is_file())
    for path in files:
        if path.is_symlink():
            raise UnsafeArchive(f"refusing to zip a symlink: {path}")
    dest_zip = Path(dest_zip)
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest_zip, "w", compresslevel=6) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(src_dir).as_posix(), FIXED_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | FILE_MODE) << 16
            info.create_system = 3  # Unix, so the mode bits above are honoured
            # Streamed, so the 886 MB dqi circuit is never held in memory.
            large = path.stat().st_size >= zipfile.ZIP64_LIMIT
            with path.open("rb") as src, archive.open(info, "w", force_zip64=large) as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
    return dest_zip
