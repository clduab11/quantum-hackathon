"""Shared path-file boundary for the project-local installer and its rollback."""
from pathlib import Path
import stat
import sys
import sysconfig

REPO = Path(__file__).resolve().parents[1]
BINARY_SHA256 = 'c66b3216c4029e0cdfd09054306aa0feadf53ab2f50c1164e37f752874e5005e'


def path_file():
    venv = REPO / '.venv'
    if (Path(sys.prefix) != venv or venv.resolve() != venv or sys.prefix == sys.base_prefix
            or sys.implementation.name != 'cpython' or sys.version_info[:2] != (3, 13)):
        raise ValueError('Run with uv run in this repository venv (.venv, CPython 3.13).')
    target = Path(sysconfig.get_path('purelib')) / 'vqcc_local.pth'
    if not target.is_relative_to(venv) or target.parent.resolve() != target.parent:
        raise ValueError('Path-file target must be inside this repository venv without linked parents.')
    return target


def path_contents(data):
    data = data.resolve()
    if '\n' in str(data) or '\r' in str(data):
        raise ValueError('Data path must not contain newline characters.')
    return f'{data / "kickmix"}\n{data / "verifiers"}\n'


def existing_matches(target, contents):
    try:
        info = target.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError('Path file must be a regular unlinked file; inspect it without modifying it.')
    if target.read_text() != contents:
        raise ValueError('Existing path file conflicts; preserve it and ask its owner to resolve it.')
    return True
