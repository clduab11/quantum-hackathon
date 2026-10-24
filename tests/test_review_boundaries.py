"""Regression checks for the calibration identity and project-only setup boundary."""
import json
from pathlib import Path

import pytest

from harness import score_local


def test_duplicate_calibration_records_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(score_local, 'fingerprint', lambda: {})
    rows = [{'environment': {}}]
    rows += [{'task': name, 'cost': 1} for name in ('invsqrt', 'dqi', 'dfthcsos', 'invsqrt')]
    rows += [{'complete': True}]
    path = tmp_path / 'baseline.jsonl'
    path.write_text('\n'.join(map(json.dumps, rows)))
    with pytest.raises(ValueError):
        score_local.load_baseline(path)


def test_install_refuses_other_venv(monkeypatch, tmp_path):
    from scripts.install_kickmix import path_file
    monkeypatch.setattr('sys.prefix', str(tmp_path))
    with pytest.raises(ValueError, match='repository venv'):
        path_file()
