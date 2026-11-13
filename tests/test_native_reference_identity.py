"""Reference names use portable manifest paths, independent of host separators."""
from pathlib import Path

import yaml

from harness import reference_identity


def test_expected_reference_names_are_posix_on_windows(tmp_path, monkeypatch):
    manifest = tmp_path / 'artifacts.yaml'
    manifest.write_text(yaml.safe_dump({'reference_files': [{
        'path': 'sample_submission/dfthcsos/angle_k_0.kmb',
        'bytes': 12,
        'sha256': 'a' * 64,
    }]}))
    monkeypatch.setattr(reference_identity, 'MANIFEST', manifest)

    assert reference_identity.expected_reference() == {
        'dfthcsos/angle_k_0.kmb': {'bytes': 12, 'sha256': 'a' * 64},
    }
