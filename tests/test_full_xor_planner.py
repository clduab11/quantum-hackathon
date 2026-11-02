"""PRA-359: our own full-XOR J=5 planner, its cache phasing and the 128-qubit gate inside the search."""
import ast
import json
import os
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tasks.dfthcsos.full_xor import gf2, planner, words as word_tools
from tasks.dfthcsos.full_xor.paired_anf import make_plan
from tasks.dfthcsos.full_xor.phasing import lower_bound, pure_monomials, search_schedule
from tasks.dfthcsos.full_xor.planio import plan_dict, plan_from_dict
from tasks.dfthcsos.full_xor.planner import PlannerConfig, WidthGateError, plan_delta
from tasks.dfthcsos.full_xor.scheduler import audit, make_schedule
from tasks.dfthcsos.generate import DEFAULT_DATA

ROOT = Path(__file__).resolve().parents[1]
FULL_XOR = ROOT / 'tasks' / 'dfthcsos' / 'full_xor'
FAST = PlannerConfig(restarts=2, schedule_effort=120, seed=7)


def canonical_table(addresses, brot, seed):
    """Sign-encoded words: the two top bits agree, as the emitter requires."""
    rng = np.random.default_rng(seed)
    half = 1 << (brot - 2)
    return (rng.integers(-half, half, size=(addresses, 5)) % (1 << brot)).astype(np.int64)


# --- GF(2) -----------------------------------------------------------------------------------------

def test_gf2_nullspace_is_orthogonal_and_complete():
    rng = random.Random(3)
    rows = [rng.getrandbits(20) for _ in range(9)]
    null = gf2.nullspace(rows, 20)
    assert len(null) == 20 - len(gf2.span_basis(rows))
    assert all(bin(r & f).count('1') % 2 == 0 for r in rows for f in null)
    assert len(gf2.span_basis(null)) == len(null)


def test_gf2_canonical_identifies_a_subspace_and_combinations_solve():
    a, b, c = 0b1011, 0b0110, 0b1101
    assert gf2.canonical([a, b]) == gf2.canonical([a ^ b, b]) == gf2.canonical([b, a, a ^ b])
    assert gf2.canonical([a, b]) != gf2.canonical([a, c ^ a ^ b ^ 1])
    combos = gf2.Combinations([a, b, a ^ b])          # the third generator is dependent
    mask = combos.solve(a ^ 0b0000)
    assert mask is not None
    rebuilt = 0
    for i, g in enumerate([a, b, a ^ b]):
        if (mask >> i) & 1:
            rebuilt ^= g
    assert rebuilt == a
    assert combos.solve(0b10000) is None


# --- exactness -------------------------------------------------------------------------------------

def test_plan_is_exact_and_beats_the_rank_split():
    delta = canonical_table(300, 8, 1)
    result = plan_delta(delta.tolist(), 8, FAST)
    from tasks.dfthcsos.full_xor.validation import independent_truth
    expected = [sum(int(x) << (j * 8) for j, x in enumerate(row)) for row in delta]
    assert independent_truth(result.plan) == expected
    baseline = make_plan(delta, 8, 4, in_place_parity=True)
    assert len(result.plan.products) < len(baseline.products)
    assert result.report['qubits'] <= 128
    audit(result.plan, result.schedule)


@pytest.mark.parametrize('brot,seed', [(8, 5), (7, 6)])
def test_emitted_circuit_is_an_exact_xor_oracle_on_dirty_targets(brot, seed):
    km = pytest.importorskip('kickmix')
    from dfthcsos.scoreinfra.circuits import _check_state, register_layout
    from tasks.dfthcsos.full_xor.emitter import build_staged
    delta = canonical_table(260, brot, seed)
    result = plan_delta(delta.tolist(), brot, FAST)
    circuit, meta = build_staged(result.plan, result.schedule)
    assert (meta['T'], meta['Q']) == (result.report['toffolis'], result.report['qubits'])
    rows = len(delta)
    layout = register_layout([circuit])
    addresses = np.tile(np.arange(rows), 3)
    selection = ((addresses[None, :] >> np.arange(len(layout.selection))[:, None]) & 1).astype(bool)
    dirty = np.random.default_rng(seed).integers(0, 1 << brot, size=(len(addresses), 5), dtype=np.int64)
    sim = km.Simulator(batch_size=len(addresses), seed=seed, counting_operations=True)
    sim.use_same_registers_as(circuit)
    sim.write_across_shots(layout.selection, selection)
    for j, word in enumerate(layout.words):
        sim.write_across_shots(word, ((dirty[:, j][None, :] >> np.arange(brot)[:, None]) & 1).astype(bool))
    table = delta[addresses]
    for expected in (dirty ^ table, dirty):
        sim.do(circuit)
        _check_state(sim, circuit, layout, selection, 'PRA-359 dirty XOR')
        actual = np.stack([(1 << np.arange(brot)) @ sim.read_across_shots(w).astype(np.int64)
                           for w in layout.words], axis=1)
        np.testing.assert_array_equal(actual, expected)


def test_plan_rows_round_trip_through_planio_for_brot_7_and_8_only():
    for brot in (7, 8):
        result = plan_delta(canonical_table(200, brot, 2).tolist(), brot, FAST)
        again = plan_from_dict(json.loads(json.dumps(plan_dict(result.plan))))
        assert plan_dict(again) == plan_dict(result.plan)
    broken = plan_dict(result.plan)
    broken['brot'] = 6
    with pytest.raises(ValueError, match='unsupported carry Plan layout'):
        plan_from_dict(broken)


def test_a_table_the_emitter_refuses_is_still_planned_and_exact():
    """Half-up brot-7 words can have differing top bits; the planner prices them, the emitter refuses."""
    from tasks.dfthcsos.full_xor.emitter import build_staged
    delta = canonical_table(200, 7, 4)
    delta[3, 0] = 32                       # bit 6 = 0, bit 5 = 1
    result = plan_delta(delta.tolist(), 7, FAST)
    assert result.report['outputs'] >= 31
    with pytest.raises(ValueError, match='canonical sign encoded'):
        build_staged(result.plan, result.schedule)


# --- the 128-qubit gate lives in the search --------------------------------------------------------

def test_width_formula_matches_what_the_emitter_allocates():
    from tasks.dfthcsos.full_xor.emitter import build_staged
    result = plan_delta(canonical_table(220, 8, 9).tolist(), 8, FAST)
    _, meta = build_staged(result.plan, result.schedule)
    assert planner.peak_width(result.plan, result.schedule['capacity']) == meta['Q']


def test_check_width_boundary():
    result = plan_delta(canonical_table(220, 8, 9).tolist(), 8, FAST)
    cap = result.schedule['capacity']
    width = planner.peak_width(result.plan, cap)
    assert planner.check_width(result.plan, cap, width) == width
    with pytest.raises(WidthGateError):
        planner.check_width(result.plan, cap, width - 1)


def test_over_width_table_emits_nothing_and_never_reaches_the_emitter(monkeypatch):
    """A cap below the words plus selection: rejected before any block is solved or circuit built."""
    from tasks.dfthcsos.full_xor import emitter, search_plans
    calls = []
    monkeypatch.setattr(emitter, 'build_staged', lambda *a, **k: calls.append('emit'))
    monkeypatch.setattr(planner, 'plan_from_blocks', lambda *a, **k: calls.append('search'))
    delta = canonical_table(300, 8, 1)
    with pytest.raises(WidthGateError):
        plan_delta(delta.tolist(), 8, PlannerConfig(max_width=40))
    with pytest.raises(WidthGateError):
        search_plans.search(np.tile(delta, (1, 15)), 8, PlannerConfig(max_width=40), workers=1, emit=True)
    assert calls == []


def test_over_width_schedule_is_rejected_before_emission(monkeypatch):
    """The words and selection fit, but the cache does not: the plan is found, the schedule is refused."""
    from tasks.dfthcsos.full_xor import emitter
    calls = []
    monkeypatch.setattr(emitter, 'build_staged', lambda *a, **k: calls.append('emit'))
    delta = canonical_table(300, 8, 1)
    fit = plan_delta(delta.tolist(), 8, FAST)
    fixed = planner.fixed_width(fit.plan.addresses, 8, planner.high_cache_size(fit.plan))
    tight = fixed + planner.min_capacity(fit.plan) - 1
    with pytest.raises(WidthGateError):
        plan_delta(delta.tolist(), 8, PlannerConfig(restarts=2, schedule_effort=40, seed=7, max_width=tight))
    with pytest.raises(WidthGateError):
        planner.schedule_within_width(fit.plan, tight, random.Random(0), 40)
    assert calls == []
    # one slot more and the same search succeeds, within the cap it was given
    ok = plan_delta(delta.tolist(), 8, PlannerConfig(restarts=2, schedule_effort=40, seed=7, max_width=tight + 1))
    assert ok.report['qubits'] <= tight + 1


def test_blocks_that_need_more_slots_than_the_gate_leaves_are_not_offered():
    tensor = planner.build_tensor(canonical_table(300, 8, 3).tolist(), 8)
    with pytest.raises(WidthGateError):
        planner.candidate_blocks(tensor, random.Random(0), 0, (3, 4), slots=1)


def test_width_gate_fires_under_optimize():
    code = (
        'from tasks.dfthcsos.full_xor.planner import PlannerConfig, WidthGateError, plan_delta\n'
        'import numpy as np\n'
        'delta = (np.random.default_rng(1).integers(-64, 64, size=(300, 5)) % 256).tolist()\n'
        'try:\n'
        '    plan_delta(delta, 8, PlannerConfig(max_width=60))\n'
        'except WidthGateError:\n'
        '    raise SystemExit(0)\n'
        'raise SystemExit("did not raise")\n')
    env = {**os.environ, 'PYTHONPATH': str(ROOT) + os.pathsep + os.environ.get('PYTHONPATH', '')}
    env.pop('PYTHONOPTIMIZE', None)
    done = subprocess.run([sys.executable, '-O', '-c', code], cwd=ROOT, env=env, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr or done.stdout


def test_planner_modules_contain_no_assert():
    """`python -O` strips Assert nodes; none of our checks may rely on one."""
    for name in ('planner.py', 'phasing.py', 'gf2.py', 'words.py', 'search_plans.py'):
        tree = ast.parse((FULL_XOR / name).read_text())
        assert [n for n in ast.walk(tree) if isinstance(n, ast.Assert)] == [], name


# --- cache phasing ---------------------------------------------------------------------------------

def test_phased_schedule_is_audited_and_no_worse_than_end_loaded_pure_terms():
    result = plan_delta(canonical_table(300, 8, 11).tolist(), 8, FAST)
    plan = result.plan
    capacity = max(planner.min_capacity(plan), 6)
    phased = search_schedule(plan, capacity, random.Random(1), 200)
    old, _ = make_schedule(plan, capacity)
    audit(plan, phased)
    assert phased['low_computations'] <= old['low_computations']
    assert phased['low_computations'] >= lower_bound(plan)
    placed = [e['monomial'] for e in phased['events'] if e['kind'] == 'pure_low']
    assert sorted(placed) == sorted(pure_monomials(plan))


# --- word tables -----------------------------------------------------------------------------------

def test_half_up_requantize_and_the_one_step_clamp():
    w8 = np.arange(-64, 64) % 256                      # every canonical 8-bit word
    w7 = word_tools.requantize(w8, 8, 7)
    by_input = dict(zip(w8.tolist(), w7.tolist()))
    assert by_input[63] == 32 and by_input[62] == 31 and by_input[0] == 0 and by_input[192] == 96
    assert word_tools.noncanonical(w7, 7).sum() == 1   # only 63 -> 32 leaves the sign-encoded range
    clamped = word_tools.clamp_canonical(w7, 7)
    assert clamped[w8 == 63][0] == 31 and not word_tools.noncanonical(clamped, 7).any()
    assert np.array_equal(word_tools.requantize(w8, 8, 8), w8)


# --- the published (8,143,60) factor ---------------------------------------------------------------

def _factor_words():
    from tasks.dfthcsos import b143
    source = Path(DEFAULT_DATA) / b143.INPUT_PATH
    if not source.is_file():
        pytest.skip(f'declared B143 input not staged at {source}')
    from tasks.dfthcsos.generate import sha256_file
    if sha256_file(source) != b143.INPUT_SHA256:
        pytest.skip('staged B143 input does not match its pin')
    with np.load(source, allow_pickle=False) as archive:
        return np.asarray(archive['angle_words'])


def test_b143_coded_batch_plans_are_exact_and_fit_128_qubits():
    pytest.importorskip('kickmix')
    from tasks.dfthcsos.b143 import batch_deltas
    from tasks.dfthcsos.full_xor.emitter import build_staged
    delta = batch_deltas(_factor_words())[:, 5]
    result = plan_delta(delta.tolist(), 8, PlannerConfig(seed=1))
    circuit, meta = build_staged(result.plan, result.schedule)
    assert meta['Q'] <= 128 and meta['T'] == result.report['toffolis']
    assert result.report['low_computations'] == 11
    # the rank split in make_plan needs 238 products here, the committed plan 180
    assert len(result.plan.products) <= 195
