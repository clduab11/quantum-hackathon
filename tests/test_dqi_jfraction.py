from tasks.dqi.jfraction.gates import g1_smoke
import hashlib
import json
from pathlib import Path


def test_norm_recycle_inverse_restores_value_and_phase():
    report = g1_smoke(None)
    assert report['status'] == 'PASS', report
    assert report['inverse_cleanup_shots'] == 80


def test_port_matches_declared_source_map_and_excludes_notebook_drivers():
    root = Path(__file__).resolve().parents[1]
    port = root / 'tasks/dqi/jfraction'
    source_map = json.loads((port / 'SOURCE_MAP.json').read_text())
    for item in source_map['files']:
        path = port / item['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item['port_sha256'], path
    for path in port.glob('*.py'):
        source = path.read_text()
        assert 'Circuit.from_file' not in source
        assert 'verify-only' not in source
        assert '/kaggle/' not in source
    assert not (port / 'mask_projection.py').exists()
    assert not (port / 'build_projected_dqi.py').exists()
