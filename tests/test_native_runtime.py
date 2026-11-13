"""Native Windows setup must not depend on the competition's Linux extension."""
from pathlib import Path
import sys

import pytest

from scripts import install_kickmix, kickmix_paths


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows PyPI wheel integration')
def test_windows_installer_uses_pypi_without_linux_binary(tmp_path, monkeypatch):
    data = tmp_path / 'package'
    verifier = data / 'verifiers/dqi/verify_submission_dqi.py'
    verifier.parent.mkdir(parents=True)
    verifier.write_text('# Native setup test; no Linux extension is supplied.\n')
    target = tmp_path / 'vqcc_local.pth'
    monkeypatch.setattr(install_kickmix, 'path_file', lambda: target)
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(sys, 'argv', ['install_kickmix.py', str(data)])

    assert install_kickmix.main() == 0
    assert target.read_text() == kickmix_paths.path_contents(data)
    import importlib.metadata
    import kickmix
    assert importlib.metadata.version('kickmix') == '1.0.0'
    assert Path(kickmix.__file__).suffix == '.pyd'
