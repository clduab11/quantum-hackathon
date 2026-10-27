"""PRA-294 J=4 streamed lookup: dirty targets, phase, inverse, plan determinism, pins and floor."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = Path('/home/cld-main/work/vqcc-data')


def _c59_words():
    from tasks.dfthcsos import c59
    source = DATA / c59.INPUT_PATH
    if not source.is_file():
        pytest.skip(f'declared C59 input not staged at {source}')
    with np.load(source, allow_pickle=False) as archive:
        return archive['angle_words'], archive['tree_edges']


def test_batch_dirty_xor_phase_and_inverse():
    km = pytest.importorskip('kickmix')
    from dfthcsos.scoreinfra.circuits import register_layout, _check_state
    from tasks.dfthcsos.c59 import FIRST_STAGE_SEEDS, compile_batch
    from tasks.dfthcsos.generate import batch_deltas
    words, _ = _c59_words()
    k = 7
    table = batch_deltas(words, 4)[k]
    circuit, report = compile_batch(table, FIRST_STAGE_SEEDS[k])
    assert (report['toffoli_per_call'], report['num_qubits']) == (274, 128)
    rows = len(table)
    rng = np.random.default_rng(294)
    layout = register_layout([circuit])
    addresses = np.tile(np.arange(rows), 8)
    selection = ((addresses[None, :] >> np.arange(len(layout.selection))[:, None]) & 1).astype(bool)
    dirty = rng.integers(0, 256, size=(len(addresses), 4), dtype=np.int64)
    sim = km.Simulator(batch_size=len(addresses), seed=294, counting_operations=True)
    sim.use_same_registers_as(circuit)
    sim.write_across_shots(layout.selection, selection)
    for j, word in enumerate(layout.words):
        sim.write_across_shots(word, ((dirty[:, j][None, :] >> np.arange(8)[:, None]) & 1).astype(bool))
    for expected in (dirty ^ table[addresses], dirty):
        sim.do(circuit)
        _check_state(sim, circuit, layout, selection, 'PRA-294 dirty XOR')
        actual = np.stack([(1 << np.arange(8)) @ sim.read_across_shots(w).astype(np.int64)
                           for w in layout.words], axis=1)
        np.testing.assert_array_equal(actual, expected)


def test_plans_are_exact_and_seed_deterministic():
    from tasks.dfthcsos.c59 import FIRST_STAGE, FIRST_STAGE_SEEDS, SECOND_STAGE
    from tasks.dfthcsos.generate import batch_deltas
    from tasks.dfthcsos.kernel_plan import plan_balanced, plan_tensor
    from tasks.dfthcsos.paired_algebra import coefficients
    words, _ = _c59_words()
    ac = coefficients(batch_deltas(words, 4)[1], 8, 4)
    left, report = plan_balanced(ac[1:, 1:12, :], seed=FIRST_STAGE_SEEDS[1], **FIRST_STAGE)
    assert report['exact_tensor_reconstruction'] and left == plan_balanced(
        ac[1:, 1:12, :], seed=FIRST_STAGE_SEEDS[1], **FIRST_STAGE)[0]
    right, report = plan_tensor(ac[1:, 12:16, :], **SECOND_STAGE)
    assert report['exact_tensor_reconstruction'] and len(right) == report['pairs']
    # Too many relations leave no full-rank template span: the planner says so, it does not guess.
    assert plan_tensor(ac[1:, 12:16, :], **{**SECOND_STAGE, 'nrelations': 40})[0] is None


def test_emitter_rejects_other_layouts():
    pytest.importorskip('kickmix')
    from tasks.dfthcsos.paired_algebra import coefficients
    from tasks.dfthcsos.streamed_qrom import build_streamed
    three = np.zeros((64, 3), dtype=np.int64)
    with pytest.raises(ValueError, match='four eight-bit words'):
        build_streamed(three, coefficients(three, 8, 4), [[], []])
    four = np.zeros((64, 4), dtype=np.int64)
    with pytest.raises(ValueError, match='four low selection bits'):
        build_streamed(four, coefficients(four, 8, 3), [[], []])
    with pytest.raises(ValueError, match='redundant sign-bit'):
        build_streamed(np.full((64, 4), 128, dtype=np.int64), coefficients(four, 8, 4), [[], []])


def test_input_pin_rejects_before_writes(tmp_path):
    from tasks.dfthcsos import c59
    source = tmp_path / c59.INPUT_PATH
    source.parent.mkdir(parents=True)
    source.write_bytes(b'changed input')
    with pytest.raises(ValueError, match='SHA-256'):
        c59.generate(tmp_path / 'out', data=tmp_path)
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('ratio,expected', [(7.9999, 'FAIL'), (float('nan'), 'FAIL'),
                                           (None, 'FAIL'), (8.0, 'PASS')])
def test_measured_floor(monkeypatch, ratio, expected):
    from tasks.dfthcsos import c59_gates
    from tasks.dqi.fused import gates
    monkeypatch.setattr(gates, 'g4_floor_on_port', lambda _: {'status': 'PASS'})
    ctx = SimpleNamespace(manifest=SimpleNamespace(tasks={'dfthcsos': SimpleNamespace(ratio=ratio)}))
    assert c59_gates.g4_floor(ctx)['status'].startswith(expected)
    monkeypatch.setattr(gates, 'g4_floor_on_port', lambda _: {'status': 'FAIL: dqi'})
    assert c59_gates.g4_floor(ctx)['status'] == 'FAIL: dqi'


def test_bundle_config_changes_only_chemistry_from_pra293():
    from ledger.gates.runner import load_config
    from tasks.dfthcsos import c59
    base = yaml.safe_load((ROOT / 'configs/gates/pra293-fused-invsqrt.yaml').read_text())
    for gate in base['gates']:
        if gate['id'] == 'G1':
            gate['params']['hooks']['dfthcsos'] = 'tasks.dfthcsos.c59_gates:g1_smoke'
        if gate['id'] == 'G4':
            gate['check'] = 'tasks.dfthcsos.c59_gates:g4_floor'
    base['generators']['dfthcsos'] = ['{python}', '-m', 'tasks.dfthcsos.c59', '--out', '{out}']
    base['inputs']['dfthcsos'] = [{'path': str(c59.INPUT_PATH), 'sha256': c59.INPUT_SHA256}]
    path = ROOT / 'configs/gates/pra294-c59.yaml'
    assert yaml.safe_load(path.read_text()) == base
    config = load_config(path)
    assert config.spec('G3').params['expected_shots']['dfthcsos'] == 1366 * 64
    assert all(not spec.waivable for spec in config.gates)
    assert len(c59.FIRST_STAGE_SEEDS) == 19
