"""Fail closed on tampered downloads and changed sibling tasks."""
import hashlib
from types import SimpleNamespace

import pytest

from tasks.invsqrt.vendored import generate, gates


def test_stage_rejects_changed_source_without_overwriting(tmp_path, monkeypatch):
    source = tmp_path / 'source.kmb'
    source.write_bytes(b'tampered')
    out = tmp_path / 'out'
    out.mkdir()
    (out / 'invsqrt.kmb').write_bytes(b'previous')
    monkeypatch.setattr(generate, 'SHA256', hashlib.sha256(b'accepted').hexdigest())
    with pytest.raises(ValueError, match='SHA-256'):
        generate.stage(source, out)
    assert (out / 'invsqrt.kmb').read_bytes() == b'previous'


def test_stage_copies_only_pinned_bytes(tmp_path, monkeypatch):
    source = tmp_path / 'source.kmb'
    source.write_bytes(b'accepted')
    monkeypatch.setattr(generate, 'SHA256', hashlib.sha256(b'accepted').hexdigest())
    generate.stage(source, tmp_path / 'out')
    assert (tmp_path / 'out/invsqrt.kmb').read_bytes() == b'accepted'
    assert [p.name for p in (tmp_path / 'out').iterdir()] == ['invsqrt.kmb']


def test_g1_rejects_wrong_bytes_before_parsing(tmp_path):
    (tmp_path / 'invsqrt.kmb').write_bytes(b'not the selected circuit')
    assert gates.g1_smoke(tmp_path)['status'].startswith('FAIL')


def test_g4_rejects_changed_sibling_even_when_score_improves(monkeypatch):
    parent = SimpleNamespace(tasks={t: SimpleNamespace(files={'file': t}) for t in ('dqi', 'dfthcsos')})
    manifest = SimpleNamespace(parent_candidate_id='pra309-chem-8-143-60', tasks={
        'invsqrt': SimpleNamespace(files={'invsqrt.kmb': generate.SHA256}, ratio=20.06),
        'dqi': SimpleNamespace(files={'file': 'changed'}, ratio=54.73),
        'dfthcsos': SimpleNamespace(files={'file': 'dfthcsos'}, ratio=9.778),
    })
    monkeypatch.setattr(gates, 'read_manifest', lambda _: parent)
    monkeypatch.setattr(gates, 'g4_strict_improvement', lambda _: {'status': 'PASS'})
    ctx = SimpleNamespace(manifest=manifest, manifests_root=__import__('pathlib').Path('.'))
    assert gates.g4_floor(ctx)['status'].startswith('FAIL')
