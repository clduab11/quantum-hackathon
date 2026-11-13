"""Native state replacement must survive short NTFS sharing conflicts."""
import json
from pathlib import Path

import pytest

from scripts import paperclip_killswitch as ks


def test_atomic_write_retries_transient_windows_replace_conflict(tmp_path, monkeypatch):
    state = tmp_path / 'state.json'
    state.write_text('{"previous": true}', encoding='utf-8')
    real_replace = ks.os.replace
    attempts = []

    def sharing_conflict_then_replace(source, destination):
        attempts.append(Path(source))
        assert json.loads(state.read_text(encoding='utf-8')) == {'previous': True}
        if len(attempts) < 3:
            error = PermissionError('temporary Windows sharing conflict')
            error.winerror = 32
            raise error
        return real_replace(source, destination)

    monkeypatch.setattr(ks.os, 'replace', sharing_conflict_then_replace)
    ks._atomic_write(state, '{"complete": true}')
    assert len(attempts) == 3 and len(set(attempts)) == 1
    assert json.loads(state.read_text(encoding='utf-8')) == {'complete': True}


def test_atomic_write_does_not_retry_unrelated_permission_failure(tmp_path, monkeypatch):
    state = tmp_path / 'state.json'
    state.write_text('{"previous": true}', encoding='utf-8')
    attempts = []

    def permanent_error(source, destination):
        attempts.append(Path(source))
        raise PermissionError('ordinary access denial')

    monkeypatch.setattr(ks.os, 'replace', permanent_error)
    with pytest.raises(PermissionError, match='ordinary access denial'):
        ks._atomic_write(state, '{"complete": true}')
    assert len(attempts) == 1
    assert json.loads(state.read_text(encoding='utf-8')) == {'previous': True}
