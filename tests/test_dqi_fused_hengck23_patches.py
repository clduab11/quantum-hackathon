# SPDX-License-Identifier: Apache-2.0
"""PRA-322: hengck23 edit layer keeps vendored pins true and fails on bad trees."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from tasks.dqi.fused.patches import apply_patches
from tasks.dqi.fused.patches import e001_phase_zero_condition as e001
from tasks.dqi.fused.patches import e002_projective_extract as e002
from tasks.dqi.fused.patches import e011_clear_flag_by_measurement as e011
from tasks.dqi import generate_fused

ROOT = Path(__file__).resolve().parents[1]
FUSED = ROOT / 'tasks/dqi/fused'
SOURCE = FUSED / 'source'


def sha256(path: Path) -> str:
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def test_vendored_pins_still_match_source_map():
    files = json.loads((FUSED / 'SOURCE_MAP.json').read_text())['files']
    drift = [item['file'] for item in files if sha256(FUSED / item['file']) != item['port_sha256']]
    assert drift == []


def test_apply_patches_requires_a_real_source_tree(tmp_path):
    empty = tmp_path / 'empty'
    empty.mkdir()
    with pytest.raises(SystemExit, match='missing build.py'):
        apply_patches(empty)


def test_e001_fails_when_marker_missing(tmp_path):
    tree = tmp_path / 'source'
    shutil.copytree(SOURCE, tree)
    target = tree / e001.RELPATH
    target.write_text('def not_phase_zero():\n    return None\n')
    with pytest.raises(SystemExit, match='e001: marker not found'):
        e001.apply(tree)


def test_e001_rewrites_phase_zero_on_a_scratch_copy(tmp_path):
    tree = tmp_path / 'source'
    shutil.copytree(SOURCE, tree)
    before = (tree / e001.RELPATH).read_text()
    assert 'push_condition(mask)' not in before
    receipt = e001.apply(tree)
    after = (tree / e001.RELPATH).read_text()
    assert receipt['edit'] == 'e001'
    assert receipt['expected_dT'] == -374
    assert 'push_condition(mask)' in after
    assert 'b.cz(ladder[-1],y[-1])' in after
    # Vendored original untouched.
    assert 'push_condition(mask)' not in (SOURCE / e001.RELPATH).read_text()


def test_stage_source_without_edits_is_byte_identical(tmp_path):
    scratch = tmp_path / 'scratch'
    scratch.mkdir()
    receipts = generate_fused.stage_source(scratch, apply_hengck23=False)
    assert receipts == []
    original = SOURCE / 'exp/arithmetic/division.py'
    staged = scratch / 'source/exp/arithmetic/division.py'
    assert sha256(original) == sha256(staged)


def test_stage_source_with_edits_patches_only_the_copy(tmp_path):
    scratch = tmp_path / 'scratch'
    scratch.mkdir()
    receipts = generate_fused.stage_source(scratch, apply_hengck23=True)
    assert [r['edit'] for r in receipts] == ['e001', 'e011']
    original = SOURCE / 'exp/arithmetic/division.py'
    staged = scratch / 'source/exp/arithmetic/division.py'
    assert sha256(original) != sha256(staged)
    assert 'push_condition(mask)' in staged.read_text()
    assert 'push_condition(mask)' not in original.read_text()
    extract = (scratch / 'source/exp/confluent_extract/kernel.py').read_text()
    assert 'projective_thresh' not in extract


def test_experimental_e002_is_opt_in_and_patches_only_the_copy(tmp_path):
    tree = tmp_path / 'source'
    shutil.copytree(SOURCE, tree)
    receipts = apply_patches(tree, experimental=True)
    assert [r['edit'] for r in receipts] == ['e001', 'e011', 'e002']
    assert 'projective_thresh' in (tree / 'exp/confluent_extract/kernel.py').read_text()
    assert 'projective_thresh' not in (SOURCE / 'exp/confluent_extract/kernel.py').read_text()


def test_e002_fails_when_marker_missing(tmp_path):
    tree = tmp_path / 'source'
    shutil.copytree(SOURCE, tree)
    target = tree / e002.RELPATH
    target.write_text('def not_extract():\n    return None\n')
    with pytest.raises(SystemExit, match='e002: marker not found'):
        e002.apply(tree)


def test_e002_rewrites_extract_on_a_scratch_copy(tmp_path):
    tree = tmp_path / 'source'
    shutil.copytree(SOURCE, tree)
    before = (tree / e002.RELPATH).read_text()
    assert 'projective_thresh' not in before
    receipt = e002.apply(tree)
    after = (tree / e002.RELPATH).read_text()
    assert receipt['edit'] == 'e002'
    assert receipt['expected_dT'] == -15259
    assert receipt['expected_dQ'] == 12
    assert 'projective_thresh=5' in after
    assert 'park_W' in after
    assert 'projective_thresh' not in (SOURCE / e002.RELPATH).read_text()


def test_projective_classical_matches_affine_extract_and_keeps_16_jets(monkeypatch):
    import importlib.util

    # Importing the vendored source must not leave __pycache__ in it (pin closure test).
    monkeypatch.setattr(sys, 'dont_write_bytecode', True)

    path = ROOT / 'ledger/evidence/pra322-hengck23/projective_classical.py'
    spec = importlib.util.spec_from_file_location('pra322_projective_classical', path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    result = mod.self_check(repeats=8)
    assert result['matches'] == result['repeats']
    assert result['full_jets_at_thresh'] == 16
    assert result['total_jets'] == 289


def test_e011_fails_when_a_site_is_missing(tmp_path):
    tree = tmp_path / 'source'
    shutil.copytree(SOURCE, tree)
    target = tree / e011.SHORT
    target.write_text(target.read_text().replace('old.clear_flag(b,g[-1],F)', 'old.something_else(b,g[-1],F)'))
    with pytest.raises(SystemExit, match='e011: site root_a not found exactly once'):
        e011.apply(tree)


def test_e011_fails_when_marker_missing(tmp_path):
    tree = tmp_path / 'source'
    shutil.copytree(SOURCE, tree)
    (tree / e011.CONVERTER).write_text('def not_clear_flag():\n    return None\n')
    with pytest.raises(SystemExit, match='e011: marker not found'):
        e011.apply(tree)


def test_e011_switches_every_clear_flag_call_to_the_measured_clear(tmp_path):
    tree = tmp_path / 'source'
    shutil.copytree(SOURCE, tree)
    receipt = e011.apply(tree)
    assert receipt['edit'] == 'e011'
    assert receipt['sites'] == ['q_post', 'look_a', 'look_b', 'root_a', 'root_b']
    converter = (tree / e011.CONVERTER).read_text()
    short = (tree / e011.SHORT).read_text()
    assert 'def clear_flag_m' in converter and 'b.hmr(F,m[0])' in converter
    # Only the original definition keeps the recompute; no call site does.
    assert converter.count('clear_flag(') == 1
    assert 'clear_flag(' not in short
    assert 'clear_flag(' in (SOURCE / e011.CONVERTER).read_text()
