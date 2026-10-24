from pathlib import Path
import sys

import pytest

from scripts import install_kickmix, kickmix_paths, uninstall_kickmix
from harness.runtime import DATA


@pytest.fixture
def target(tmp_path, monkeypatch):
    monkeypatch.setattr(kickmix_paths, 'REPO', tmp_path)
    venv = tmp_path / '.venv'
    purelib = venv / 'lib/python3.13/site-packages'
    purelib.mkdir(parents=True)
    monkeypatch.setattr(sys, 'prefix', str(venv))
    monkeypatch.setattr(kickmix_paths.sysconfig, 'get_path', lambda _: str(purelib))
    return purelib / 'vqcc_local.pth'


def invoke(monkeypatch, module, *args):
    monkeypatch.setattr(sys, 'argv', [module.__name__, str(DATA), *args])
    return module.main()


def test_create_reinstall_and_rollback(target, monkeypatch):
    # Real binary hash and import probe; only the destination is a scratch venv boundary.
    assert invoke(monkeypatch, install_kickmix, '--dry-run') == 0
    assert not target.exists()
    assert invoke(monkeypatch, install_kickmix) == 0
    before = target.stat()
    assert target.read_text() == kickmix_paths.path_contents(DATA)
    assert invoke(monkeypatch, install_kickmix) == 0
    assert target.stat() == before
    assert invoke(monkeypatch, uninstall_kickmix, '--dry-run') == 0
    assert target.exists()
    assert invoke(monkeypatch, uninstall_kickmix) == 0
    assert not target.exists()
    assert invoke(monkeypatch, uninstall_kickmix) == 0


def test_conflicting_contents_preserved(target, monkeypatch):
    target.write_text('existing unrelated configuration\n')
    before = target.read_bytes()
    for module in (install_kickmix, uninstall_kickmix):
        assert invoke(monkeypatch, module) == 1
        assert target.read_bytes() == before


@pytest.mark.parametrize('kind', ['symlink', 'dangling', 'hardlink', 'directory'])
def test_links_and_nonfiles_preserved(target, monkeypatch, kind):
    outside = target.parent.parent / 'other'
    outside.write_text(kickmix_paths.path_contents(DATA))
    if kind == 'symlink': target.symlink_to(outside)
    if kind == 'dangling': target.symlink_to(outside.with_name('absent'))
    if kind == 'hardlink': target.hardlink_to(outside)
    if kind == 'directory': target.mkdir()
    for module in (install_kickmix, uninstall_kickmix):
        assert invoke(monkeypatch, module) == 1
    assert outside.read_text() == kickmix_paths.path_contents(DATA)


def test_purelib_outside_venv_refused(target, monkeypatch, tmp_path):
    monkeypatch.setattr(kickmix_paths.sysconfig, 'get_path', lambda _: str(tmp_path))
    with pytest.raises(ValueError, match='inside this repository venv'):
        kickmix_paths.path_file()


def test_linked_parent_refused(target, monkeypatch):
    alias = target.parent.parent / 'linked'
    alias.symlink_to(target.parent, target_is_directory=True)
    monkeypatch.setattr(kickmix_paths.sysconfig, 'get_path', lambda _: str(alias))
    with pytest.raises(ValueError, match='linked parents'):
        kickmix_paths.path_file()
