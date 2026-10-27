"""Pins and exact arithmetic checks for the vendored fused decoder. These do not build the circuit."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'tasks/dqi/fused'
SOURCE_MAP = json.loads((PORT / 'SOURCE_MAP.json').read_text())


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_vendored_files_are_verbatim_and_pinned():
    for item in SOURCE_MAP['files']:
        digest = _sha(PORT / item['file'])
        assert digest == item['port_sha256'] == item['upstream_sha256'], item['file']
    assert SOURCE_MAP['source_sha256'] == '18d6760953783bec316ddb46266a1b5ccc50c291fbf47ec35f87c73f4d0cf2ac'


def test_vendored_set_is_exactly_the_pinned_closure():
    on_disk = {str(p.relative_to(PORT)) for p in (PORT / 'source').rglob('*') if p.is_file()}
    pinned = {item['file'] for item in SOURCE_MAP['files'] if item['file'].startswith('source/')}
    assert on_disk == pinned
    assert sum(name.endswith('.py') for name in pinned) == 54  # build.py + 53 imported modules
    assert sum(name.endswith('.json') for name in pinned) == 7
    embedded = {e['path']: e for e in json.loads((PORT / 'EMBEDDED_FILES.json').read_text())}
    assert len(embedded) == 89
    for item in SOURCE_MAP['files']:
        assert embedded[item['upstream_path']]['sha256'] == item['upstream_sha256']
        assert embedded[item['upstream_path']]['vendored']


def test_notice_and_licence_are_recorded():
    assert _sha(PORT / 'LICENSE') == _sha(ROOT / 'tasks/dqi/bm_forney/LICENSE')
    notice = (ROOT / 'notices/20-dqi.txt').read_text()
    assert SOURCE_MAP['source_sha256'] in notice and 'tasks/dqi/fused/' in notice
    assert 'Agniv Banerjee' in (PORT / 'NOTICE').read_text()


def test_g1_checks_vendored_arithmetic_on_the_complete_domain():
    from tasks.dqi.fused.gates import g1_smoke
    report = g1_smoke(None)
    assert report['status'] == 'PASS', report
    assert report['domain'] == 4096
    assert report['pinned_files'] == len(SOURCE_MAP['files'])
    assert not list((PORT / 'source').rglob('__pycache__'))
