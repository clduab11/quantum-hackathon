"""Exercise the helper cell itself; never run the expensive build in pytest."""
import hashlib
import json
from pathlib import Path

import pytest

NOTEBOOK = Path(__file__).resolve().parents[1] / 'notebooks/vqcc_submission.ipynb'


def helpers():
    assert NOTEBOOK.is_file(), 'Submission notebook with tested helper cell is required'
    notebook = json.loads(NOTEBOOK.read_text())
    cells = [c for c in notebook['cells'] if c.get('id') == 'hash-helpers']
    assert len(cells) == 1
    namespace = {}
    exec(''.join(cells[0]['source']), namespace)
    return namespace


def test_changed_byte_is_rejected(tmp_path):
    check = helpers()['check_hash']
    path = tmp_path / 'circuit.kmb'
    path.write_bytes(b'original circuit')
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert check(path, expected) == expected
    path.write_bytes(b'Original circuit')
    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        check(path, expected)


@pytest.mark.parametrize('change', ['changed', 'missing', 'extra'])
def test_submission_file_set_is_exact(tmp_path, change):
    check = helpers()['check_files']
    path = tmp_path / 'circuit.kmb'
    path.write_bytes(b'circuit')
    expected = {'circuit.kmb': hashlib.sha256(path.read_bytes()).hexdigest()}
    check(tmp_path, expected)
    if change == 'changed':
        path.write_bytes(b'Circuit')
    elif change == 'missing':
        path.unlink()
    else:
        (tmp_path / 'stale.kmb').write_bytes(b'stale')
    with pytest.raises(ValueError):
        check(tmp_path, expected)


def test_vendored_source_rejects_tampering_before_writing(tmp_path):
    restore = helpers()['restore_sources']
    source = {'tasks/build.py': 'print(1)\n'}
    hashes = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in source.items()}
    restore(tmp_path / 'valid', source, hashes)
    assert (tmp_path / 'valid/tasks/build.py').read_text() == source['tasks/build.py']
    source['tasks/build.py'] = 'print(2)\n'
    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        restore(tmp_path / 'invalid', source, hashes)
    assert not (tmp_path / 'invalid').exists()


def test_embedded_sources_and_expected_outputs_match_pinned_commit():
    import re
    import subprocess

    notebook = json.loads(NOTEBOOK.read_text())
    cell = next(c for c in notebook['cells'] if c.get('id') == 'pinned-source')
    pinned = {}
    exec(''.join(cell['source']), pinned)
    config = pinned['CONFIG']
    assert re.fullmatch('[0-9a-f]{40}', config['commit'])

    def at_commit(path):
        return subprocess.check_output(['git', 'show', f"{config['commit']}:{path}"], cwd=NOTEBOOK.parent)

    for name, source in pinned['SOURCES'].items():
        original = at_commit(name)
        assert source.encode() == original, name
        assert hashlib.sha256(original).hexdigest() == pinned['SOURCE_HASHES'][name]
    manifest_bytes = at_commit(config['manifest'])
    assert hashlib.sha256(manifest_bytes).hexdigest() == config['manifest_sha256']
    manifest = json.loads(manifest_bytes)
    assert config['files'] == {p: h for t in manifest['tasks'].values() for p, h in t['files'].items()}
    assert config['zip_sha256'] == manifest['zip_sha256']
