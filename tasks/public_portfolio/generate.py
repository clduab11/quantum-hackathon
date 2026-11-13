# SPDX-License-Identifier: Apache-2.0
"""Stage unchanged, hash-pinned public circuits. This is vendoring, not circuit generation.

Default pin map SOURCE.json: the syed3000 v12 dataset
https://www.kaggle.com/datasets/syed3000/vqcc-own-circuit-portfolio/versions/12 (Apache-2.0, record in
ledger/evidence/hermes-syed-v12/provenance.md, D-HERMES-20261112-02). ``--pin MIX-20261113.json``
selects the three-source public mix (record in ledger/evidence/hermes-mix-20261113/provenance.md,
D-HERMES-20261113-01). Authors' own-work statements are their claims, not something this
repository certified. Our own generators are not involved.

    python -m tasks.public_portfolio.generate [--pin NAME.json] --task invsqrt|dqi|dfthcsos --out DIR
                                              [--data ROOT]

A pin map names one ``input_dir``, or a ``sources`` object whose entries each name their own
``input_dir`` and every file names its ``source``. ``--pin`` takes a bare JSON file name beside this
module. Reads only the hash-pinned files of ONE task beneath ``<data>/<input_dir>/`` (``--data``
defaults to $VQCC_DATA; no network). Every pin of that task is checked (existence, size, SHA-256) before any
byte is written. Each file is streamed in chunks and hashed again while it is copied. An occupied
output fails without overwriting, and so does an output or task directory that is a symlink or
junction. Bytes are first written to ``<name>.partial`` and only renamed to the final name after
every file of the task has been re-verified. This stager never deletes: a failed run keeps its
``.partial`` files for inspection and a retry into that directory is refused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

PIN = json.loads((Path(__file__).with_name('SOURCE.json')).read_text(encoding='utf-8'))
TASKS = ('invsqrt', 'dqi', 'dfthcsos')
CHUNK = 1 << 20
PARTIAL = '.partial'
VENDORED = 'vendored_circuit'
PACKAGE_INPUT = 'package_input'
_HEX = re.compile(r'[0-9a-f]{64}')
_PIN_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*\.json')


def load_pin(name: str) -> dict:
    """The pin map `name`, a bare JSON file name beside this module (no paths, no traversal)."""
    if not isinstance(name, str) or not _PIN_NAME.fullmatch(name) or '..' in name:
        raise ValueError(f'--pin {name!r} must be a bare NAME.json file beside the stager')
    return json.loads(Path(__file__).with_name(name).read_text(encoding='utf-8'))


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _safe_relative(text, what: str) -> PurePosixPath:
    if not isinstance(text, str):
        raise ValueError(f'{what} {text!r} must be a string')
    path = PurePosixPath(str(text))
    if (not str(text) or '\\' in str(text) or path.is_absolute() or ':' in str(text)
            or any(part in ('', '.', '..') for part in str(text).split('/'))):
        raise ValueError(f'{what} {text!r} must be a plain relative path without traversal')
    return path


def validate_pin(pin: dict) -> None:
    """Fail closed on a malformed pin map. Raises ValueError listing every problem."""
    problems: list[str] = []
    if not isinstance(pin, dict):
        raise ValueError('pin map must be a JSON object')
    if not isinstance(pin.get('files'), list) or not all(isinstance(e, dict) for e in pin['files']):
        raise ValueError('pin map needs a "files" list of objects')
    several = 'sources' in pin
    if several:
        sources = pin['sources']
        if 'input_dir' in pin:
            problems.append('a pin map with "sources" must not also name a top-level input_dir')
        if not isinstance(sources, dict) or not sources:
            raise ValueError('"sources" must be a non-empty object of source objects')
        for key, source in sources.items():
            if not isinstance(source, dict):
                problems.append(f'source {key!r} must be an object')
                continue
            try:
                _safe_relative(source.get('input_dir', ''), f'source {key!r} input_dir')
            except ValueError as exc:
                problems.append(str(exc))
    else:
        try:
            _safe_relative(pin.get('input_dir', ''), 'input_dir')
        except ValueError as exc:
            problems.append(str(exc))
    seen: dict[str, set] = {'dataset_file': set(), 'output': set(), 'sha256': set()}
    for entry in pin.get('files', []):
        name = entry.get('dataset_file')
        label = f'pin {name!r}'
        if not isinstance(name, str) or not name or '/' in name or '\\' in name or name in ('.', '..'):
            problems.append(f'{label}: dataset_file must be a bare file name')
            continue
        if several and entry.get('source') not in pin['sources']:
            problems.append(f'{label}: source {entry.get("source")!r} is not one of the pinned sources')
            continue
        if not several and 'source' in entry:
            problems.append(f'{label}: names a source but the pin map has no "sources"')
        task, output = entry.get('task'), entry.get('output')
        if task not in TASKS:
            problems.append(f'{label}: unsupported task {task!r}')
        try:
            _safe_relative(output, f'{label}: output')
        except ValueError as exc:
            problems.append(str(exc))
        else:
            if output != name.replace('__', '/', 1):
                problems.append(f'{label}: output {output!r} is not the mapping of the dataset file')
            elif task in TASKS and PurePosixPath(output).parts[0].removesuffix('.kmb') != task:
                problems.append(f'{label}: output {output!r} does not belong to task {task}')
        if not isinstance(entry.get('sha256'), str) or not _HEX.fullmatch(entry['sha256']):
            problems.append(f'{label}: sha256 must be 64 lower-case hex characters')
        if not _is_int(entry.get('size_bytes')) or entry['size_bytes'] <= 0:
            problems.append(f'{label}: size_bytes must be a positive integer')
        want = VENDORED if name.endswith('.kmb') else PACKAGE_INPUT
        if entry.get('kind') != want:
            problems.append(f'{label}: kind must be {want!r}, got {entry.get("kind")!r}')
        for key, bucket in seen.items():
            value = entry.get(key)
            if key == 'dataset_file' and several:  # one name may recur in different sources
                value = f'{entry["source"]}/{value}'
            if isinstance(value, str) and value in bucket:
                problems.append(f'{label}: duplicate {key} {value}')
            elif isinstance(value, str):
                bucket.add(value)
    if problems:
        raise ValueError('; '.join(problems))


def _hash_file(path: Path) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        while chunk := stream.read(CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _input_dir(pin: dict, entry: dict) -> PurePosixPath:
    holder = pin['sources'][entry['source']] if 'sources' in pin else pin
    return PurePosixPath(holder['input_dir'])


def preflight(task: str, data: Path, pin: dict) -> list[tuple[dict, Path]]:
    """Check every pin of `task` against disk. Writes nothing. Returns [(entry, source)]."""
    if task not in TASKS:
        raise ValueError(f'unsupported task {task!r}; choose one of {", ".join(TASKS)}')
    validate_pin(pin)
    entries = sorted((e for e in pin['files'] if e['task'] == task), key=lambda e: e['output'])
    if not entries:
        raise ValueError(f'the pin map has no files for task {task}')
    plan, problems = [], []
    for entry in entries:
        source = Path(data).joinpath(*_input_dir(pin, entry).parts) / entry['dataset_file']
        if not source.is_file():
            problems.append(f'{entry["dataset_file"]}: missing at {source}')
            continue
        actual, size = _hash_file(source)
        if size != entry['size_bytes']:
            problems.append(f'{entry["dataset_file"]}: size {size} differs from pinned {entry["size_bytes"]}')
        elif actual != entry['sha256']:
            problems.append(f'{entry["dataset_file"]}: SHA-256 {actual} differs from pinned {entry["sha256"]}')
        plan.append((entry, source))
    if problems:
        raise ValueError('; '.join(problems))
    return plan


def _is_link(path: Path) -> bool:
    junction = getattr(path, 'is_junction', None)
    return path.is_symlink() or bool(junction and junction())


def _check_free(plan: list[tuple[dict, Path]], out: Path) -> None:
    if _is_link(out):
        raise FileExistsError(f'--out {out} is a symlink or junction; refusing to follow it')
    if out.exists() and not out.is_dir():
        raise FileExistsError(f'--out {out} exists and is not a directory')
    for entry, _ in plan:
        destination = out.joinpath(*PurePosixPath(entry['output']).parts)
        partial = destination.with_name(destination.name + PARTIAL)
        for taken in (destination, partial):
            if taken.exists() or _is_link(taken):
                raise FileExistsError(f'{taken} already exists; refusing to overwrite')
        for parent in destination.parents:
            if parent == out:
                break
            if _is_link(parent) or (parent.exists() and not parent.is_dir()):
                raise FileExistsError(f'{parent} exists and is not a directory')
    folders = {PurePosixPath(e['output']).parts[0] for e, _ in plan if '/' in e['output']}
    for name in folders:
        if (out / name).is_dir() and any((out / name).iterdir()):
            raise FileExistsError(f'{out / name} is not empty; refusing to mix files into it')


def _make_dirs(path: Path) -> None:
    missing = []
    for parent in (path, *path.parents):
        if parent.exists():
            break
        missing.append(parent)
    for parent in reversed(missing):
        parent.mkdir()


def _copy(entry: dict, source: Path, destination: Path) -> None:
    digest, size = hashlib.sha256(), 0
    with source.open('rb') as src, destination.open('xb') as dst:
        while chunk := src.read(CHUNK):
            digest.update(chunk)
            size += len(chunk)
            dst.write(chunk)
    if size != entry['size_bytes'] or digest.hexdigest() != entry['sha256']:
        raise ValueError(f'{entry["dataset_file"]}: input changed while copying '
                         f'(SHA-256 {digest.hexdigest()} differs from pinned {entry["sha256"]})')


def stage(task: str, data: Path, out: Path, pin: dict | None = None) -> dict:
    """Validate all pins of `task`, then copy them into `out` at the generator output paths."""
    pin = PIN if pin is None else pin
    out = Path(out)
    plan = preflight(task, Path(data), pin)
    _check_free(plan, out)
    _make_dirs(out)
    staged: list[tuple[Path, Path]] = []
    for entry, source in plan:  # phase 1: verified bytes land only under *.partial names
        destination = out.joinpath(*PurePosixPath(entry['output']).parts)
        _make_dirs(destination.parent)
        partial = destination.with_name(destination.name + PARTIAL)
        staged.append((partial, destination))
        _copy(entry, source, partial)
    for partial, destination in staged:  # phase 2: every file verified; rename never deletes
        partial.rename(destination)
    return {'task': task, 'source_url': pin.get('source_url'), 'version': pin.get('version'),
            'files': [{'output': e['output'], **({'source': e['source']} if 'source' in e else {}),
                       'sha256': e['sha256'], 'size_bytes': e['size_bytes']} for e, _ in plan]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pin', default=None,
                        help='pin map: a bare NAME.json beside this module (default: SOURCE.json)')
    parser.add_argument('--task', required=True, choices=TASKS)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--data', type=Path, default=None,
                        help='package root holding inputs/... (default: $VQCC_DATA)')
    args = parser.parse_args(argv)
    data = args.data or (Path(os.environ['VQCC_DATA']) if os.environ.get('VQCC_DATA') else None)
    if data is None:
        parser.error('--data or $VQCC_DATA is required')
    try:
        pin = None if args.pin is None else load_pin(args.pin)
        report = stage(args.task, data, args.out, pin=pin)
    except (ValueError, OSError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
