"""PRA-321 full-XOR J=5 loader: dirty targets, recorded plans, pins and the 9.7x floor."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

from tasks.dfthcsos.generate import DEFAULT_DATA

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(DEFAULT_DATA)


def _words():
    from tasks.dfthcsos import b143
    source = DATA / b143.INPUT_PATH
    if not source.is_file():
        pytest.skip(f'declared B143 input not staged at {source}')
    with np.load(source, allow_pickle=False) as archive:
        return np.asarray(archive['angle_words'])


def test_batch_dirty_xor_matches_recorded_circuit():
    km = pytest.importorskip('kickmix')
    from dfthcsos.scoreinfra.circuits import register_layout, _check_state
    from tasks.dfthcsos.b143 import CIRCUIT_SHA256, batch_deltas, compile_batch, load_plans
    words = _words()
    k = 5  # two coded low bits: 180 products, 260 Toffolis, 128 qubits
    delta = batch_deltas(words)[:, k]
    circuit, blob, report = compile_batch(delta, load_plans()[k])
    assert (report['toffoli_per_call'], report['num_qubits'], report['products']) == (260, 128, 180)
    assert report['sha256'] == CIRCUIT_SHA256[k] == __import__('hashlib').sha256(blob).hexdigest()
    rows = len(delta)
    rng = np.random.default_rng(321)
    layout = register_layout([circuit])
    addresses = np.tile(np.arange(rows), 4)
    selection = ((addresses[None, :] >> np.arange(len(layout.selection))[:, None]) & 1).astype(bool)
    dirty = rng.integers(0, 256, size=(len(addresses), 5), dtype=np.int64)
    sim = km.Simulator(batch_size=len(addresses), seed=321, counting_operations=True)
    sim.use_same_registers_as(circuit)
    sim.write_across_shots(layout.selection, selection)
    for j, word in enumerate(layout.words):
        sim.write_across_shots(word, ((dirty[:, j][None, :] >> np.arange(8)[:, None]) & 1).astype(bool))
    table = delta[addresses]
    for expected in (dirty ^ table, dirty):
        sim.do(circuit)
        _check_state(sim, circuit, layout, selection, 'PRA-321 dirty XOR')
        actual = np.stack([(1 << np.arange(8)) @ sim.read_across_shots(w).astype(np.int64)
                           for w in layout.words], axis=1)
        np.testing.assert_array_equal(actual, expected)


def test_plans_match_the_factor_and_reject_a_bad_record():
    from tasks.dfthcsos.b143 import batch_deltas, load_plans
    from tasks.dfthcsos.full_xor.planio import plan_from_dict
    from tasks.dfthcsos.full_xor.validation import assert_independent
    words = _words()
    deltas = batch_deltas(words)
    rows = load_plans()
    assert [row['batch'] for row in rows] == list(range(15))
    plan = plan_from_dict(rows[0]['plan'])
    assert_independent(plan, deltas[:, 0])
    broken = {**rows[0]['plan'], 'batch': 4}
    with pytest.raises(ValueError, match='unsupported carry Plan layout'):
        plan_from_dict(broken)


def test_input_pin_rejects_before_writes(tmp_path):
    from tasks.dfthcsos import b143
    source = tmp_path / b143.INPUT_PATH
    source.parent.mkdir(parents=True)
    source.write_bytes(b'changed input')
    with pytest.raises(ValueError, match='SHA-256'):
        b143.generate(tmp_path / 'out', data=tmp_path)
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('ratio,expected', [(9.6999, 'FAIL'), (float('nan'), 'FAIL'),
                                           (None, 'FAIL'), (9.7, 'PASS')])
def test_measured_floor(monkeypatch, ratio, expected):
    from tasks.dfthcsos import b143_gates, c59_gates
    monkeypatch.setattr(c59_gates, 'g4_floor', lambda _: {'status': 'PASS'})
    ctx = SimpleNamespace(manifest=SimpleNamespace(tasks={'dfthcsos': SimpleNamespace(ratio=ratio)}))
    assert b143_gates.g4_floor(ctx)['status'].startswith(expected)
    monkeypatch.setattr(c59_gates, 'g4_floor', lambda _: {'status': 'FAIL: dqi'})
    assert b143_gates.g4_floor(ctx)['status'] == 'FAIL: dqi'


def test_bundle_config_changes_only_chemistry_from_submission_010():
    from ledger.gates.runner import load_config
    from tasks.dfthcsos import b143
    base = yaml.safe_load((ROOT / 'configs/gates/pra294-c59.yaml').read_text())
    for gate in base['gates']:
        if gate['id'] == 'G1':
            gate['params']['hooks']['dfthcsos'] = 'tasks.dfthcsos.b143_gates:g1_smoke'
        if gate['id'] == 'G3':
            gate['params']['expected_shots']['dfthcsos'] = 1220 * 64
        if gate['id'] == 'G4':
            gate['check'] = 'tasks.dfthcsos.b143_gates:g4_floor'
    base['generators']['dfthcsos'] = ['{python}', '-m', 'tasks.dfthcsos.b143', '--out', '{out}']
    base['inputs']['dfthcsos'] = [{'path': str(b143.INPUT_PATH), 'sha256': b143.INPUT_SHA256}]
    path = ROOT / 'configs/gates/pra309-chem-8-143-60.yaml'
    assert yaml.safe_load(path.read_text()) == base
    config = load_config(path)
    assert config.spec('G3').params['expected_shots']['dfthcsos'] == 1220 * 64
    assert all(not spec.waivable for spec in config.gates)
    assert len(b143.CIRCUIT_SHA256) == 15
