import hashlib
import json
import shutil

import pytest

from harness import calibrate_reference, reference_identity, score_local
from harness.runtime import LOCAL_SALT


@pytest.fixture
def reference(tmp_path, monkeypatch):
    root = tmp_path / 'reference'
    root.mkdir()
    (root / 'invsqrt.kmb').write_bytes(b'reference bytes')
    identity = {'invsqrt.kmb': {'bytes': 15, 'sha256': hashlib.sha256(b'reference bytes').hexdigest()}}
    monkeypatch.setattr(reference_identity, 'expected_reference', lambda: identity)
    return root, identity


def test_identical_bytes_can_move(reference, tmp_path):
    root, identity = reference
    moved = shutil.copytree(root, tmp_path / 'relocated')
    assert reference_identity.reference_identity(root) == reference_identity.reference_identity(moved) == identity


@pytest.mark.parametrize('change', ['bytes', 'missing', 'extra'])
def test_changed_reference_rejected_before_simulation(reference, monkeypatch, change):
    root, _ = reference
    if change == 'bytes':
        (root / 'invsqrt.kmb').write_bytes(b'candidate bytes')
    elif change == 'missing':
        (root / 'invsqrt.kmb').unlink()
    else:
        (root / 'extra.kmb').touch()
    def forbidden(*args):
        pytest.fail('Changed reference reached parsing or simulation')
    monkeypatch.setattr(calibrate_reference, 'parse_submission', forbidden)
    monkeypatch.setattr(calibrate_reference, 'verify_all', forbidden)
    monkeypatch.setattr('sys.argv', ['calibrate_reference.py', '--reference', str(root)])
    assert calibrate_reference.main() == 1


@pytest.fixture
def baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(score_local, 'fingerprint', lambda: {'salt': LOCAL_SALT})
    monkeypatch.setattr(score_local, 'expected_reference', lambda: {'file': 'expected hash'})
    rows = [{'environment': {'salt': LOCAL_SALT}, 'reference_files': {'file': 'expected hash'}}]
    for name in ('invsqrt', 'dqi', 'dfthcsos'):
        rows.append({'task': name, 'status': 'PASS', 'cost': 1.,
                     'full_verification': {'shot_divisor': 1, 'salt_label': LOCAL_SALT},
                     'verifier': {'status': 'PASS', 'score': 1.}})
    rows.append({'complete': True})
    def write():
        path = tmp_path / 'baseline.jsonl'
        path.write_text('\n'.join(map(json.dumps, rows)))
        return path
    return rows, write


def test_baseline_accepts_bound_full_pass(baseline):
    _, write = baseline
    assert score_local.load_baseline(write()) == dict.fromkeys(('invsqrt', 'dqi', 'dfthcsos'), 1.)


@pytest.mark.parametrize('change', ['identity', 'no_identity', 'duplicate', 'missing', 'status',
                                   'no_verifier', 'verifier_fail', 'no_status', 'no_full', 'reduced_shots', 'salt', 'cost'])
def test_bad_calibration_evidence_rejected(baseline, change):
    rows, write = baseline
    if change == 'identity': rows[0]['reference_files'] = {'file': 'different hash'}
    if change == 'no_identity': del rows[0]['reference_files']
    if change == 'duplicate': rows.insert(1, rows[1].copy())
    if change == 'missing': rows.pop(1)
    if change == 'status': rows[1]['status'] = 'FAIL'
    if change == 'no_verifier': del rows[1]['verifier']
    if change == 'verifier_fail': rows[1]['verifier']['status'] = 'FAIL'
    if change == 'no_status': del rows[1]['status']
    if change == 'no_full': del rows[1]['full_verification']
    if change == 'reduced_shots': rows[1]['full_verification']['shot_divisor'] = 2
    if change == 'salt': rows[1]['full_verification']['salt_label'] = 'other'
    if change == 'cost': rows[1]['cost'] = 2.
    with pytest.raises(ValueError):
        score_local.load_baseline(write())
