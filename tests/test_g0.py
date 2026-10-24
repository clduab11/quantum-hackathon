"""Metric file validation must reject bad input without creating a Simulator."""
import io
import zipfile

import numpy as np
import pytest

from ledger.gates.g0_preflight import preflight_zip


def npz_bytes(*, oversized=False, dtype='float64'):
    buf = io.BytesIO()
    if oversized:
        # Header-only: reject declared decoded bytes before trying to load data.
        with zipfile.ZipFile(buf, 'w') as archive:
            shapes = {'U': (200000, 1, 76), 'W': (200000, 1, 1),
                      'H2_I': (200000, 1), 'H1_I': (),
                      'Hsym_lower': (2926,), 'tree_edges': (75, 2)}
            for key, shape in shapes.items():
                header = io.BytesIO()
                np.lib.format.write_array_header_1_0(header, {
                    'descr': '<i8' if key == 'tree_edges' else '<f8',
                    'fortran_order': False, 'shape': shape})
                archive.writestr(key + '.npy', header.getvalue())
    else:
        np.savez(buf, U=np.zeros((1, 1, 76), dtype=dtype), W=np.zeros((1, 1, 1)),
                 H2_I=np.zeros((1, 1)), H1_I=np.array(0.), Hsym_lower=np.zeros(2926),
                 tree_edges=np.zeros((75, 2), dtype='int64'))
    return buf.getvalue()


def archive(tmp_path, *, instruction='', duplicate=False, oversized=False, dtype='float64'):
    path = tmp_path / 'submission.zip'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('invsqrt.kmx', 'APPEND_TO_REGISTER q0 r0\nREGISTER r0 "x"\n' + instruction)
        z.writestr('dqi.kmx', '')
        z.writestr('dfthcsos/angle_k_0.kmx', '')
        z.writestr('dfthcsos/submission.npz', npz_bytes(oversized=oversized, dtype=dtype))
        if duplicate:
            z.writestr('nested/invsqrt.kmx', 'APPEND_TO_REGISTER q0 r0\nREGISTER r0 "x"\n')
    return path


@pytest.fixture(autouse=True)
def forbid_simulation(monkeypatch):
    import kickmix
    def forbidden(*args, **kwargs):
        pytest.fail('G0 attempted simulation')
    monkeypatch.setattr(kickmix, 'Simulator', forbidden)


def test_good_zip(tmp_path):
    with preflight_zip(archive(tmp_path)) as checked:
        assert checked['invsqrt'].num_registers == 1


@pytest.mark.parametrize('options,match', [
    ({'instruction': 'INVALID q0\n'}, 'invalid'),
    ({'duplicate': True}, 'exactly one'),
    ({'oversized': True}, 'above the limit'),
    ({'dtype': 'int64'}, 'dtype'),
    ({'instruction': 'X q699050\n'}, 'above the limit'),
])
def test_bad_zip(tmp_path, options, match):
    with pytest.raises(Exception, match=match):
        with preflight_zip(archive(tmp_path, **options)):
            pytest.fail('bad ZIP passed')


def rewrite(path, changes):
    with zipfile.ZipFile(path) as z:
        members = {n: z.read(n) for n in z.namelist()}
    members.update(changes)
    with zipfile.ZipFile(path, 'w') as z:
        for name, contents in members.items():
            z.writestr(name, contents)
    return path


@pytest.mark.parametrize('text,match', [
    ('', 'exactly one named register'),
    ('APPEND_TO_REGISTER q0 r0\n', 'every register needs a name'),
    ('REGISTER r0 "x"\nREGISTER r1 "y"\n', 'registers, above'),
    ('REGISTER r0 "x"\nBIT_STORE0 b699050\n', 'above the limit'),
])
def test_registers_and_bits(tmp_path, text, match):
    path = rewrite(archive(tmp_path), {'invsqrt.kmx': text})
    with pytest.raises(Exception, match=match):
        with preflight_zip(path):
            pytest.fail('bad metadata passed')


def test_largest_legal_id(tmp_path):
    with preflight_zip(archive(tmp_path, instruction='X q699049\n')) as checked:
        assert checked['invsqrt'].num_qubits == 699050


@pytest.mark.parametrize('extra', ['dfthcsos/angle_k_0.kmb', 'dfthcsos/angle_k_2.kmx'])
def test_duplicate_format_or_angle_gap(tmp_path, extra):
    path = rewrite(archive(tmp_path), {extra: b''})
    with pytest.raises(ValueError, match='consecutive'):
        with preflight_zip(path):
            pytest.fail('bad family passed')


def test_recursive_discovery_and_macos_metadata(tmp_path):
    path = archive(tmp_path)
    with zipfile.ZipFile(path) as z:
        files = [(n, z.read(n)) for n in z.namelist()]
    with zipfile.ZipFile(path, 'w') as z:
        for name, data in files:
            z.writestr('nested/' + name, data)
            z.writestr('__MACOSX/' + name, data)
    with preflight_zip(path):
        pass


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'a\\b'])
def test_unsafe_archive_names(tmp_path, name):
    path = rewrite(archive(tmp_path), {name: b''})
    with pytest.raises(ValueError, match='Unsafe'):
        with preflight_zip(path):
            pytest.fail('unsafe archive passed')


def test_scorer_rejects_before_verifier_or_baseline(tmp_path, monkeypatch, capsys):
    from harness import score_local
    def forbidden(*args, **kwargs):
        pytest.fail('malformed ZIP reached verification or baseline')
    monkeypatch.setattr(score_local, 'verify_all', forbidden)
    monkeypatch.setattr(score_local, 'load_baseline', forbidden)
    monkeypatch.setattr('sys.argv', ['score_local.py', str(archive(tmp_path, oversized=True))])
    assert score_local.main() == 1
    captured = capsys.readouterr()
    assert 'above the limit' in captured.err
    assert 'geometric_mean' not in captured.out


def test_instruction_whitelist_is_enforced(tmp_path):
    from harness.runtime import load_metric
    metric = load_metric()
    metric.ALLOWED_INSTRUCTIONS = metric.ALLOWED_INSTRUCTIONS - {'X'}
    with pytest.raises(ValueError, match='unsupported instructions'):
        with preflight_zip(archive(tmp_path, instruction='X q0\n'), metric):
            pytest.fail('instruction outside whitelist passed')
