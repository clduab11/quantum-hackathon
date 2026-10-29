"""The budget must reject a cheap-looking layout with too many allocated ids."""
import math
import subprocess
import sys

import pytest


def test_design_gate_cli_rejects_unmet_target():
    result = subprocess.run(
        [sys.executable, '-m', 'tasks.invsqrt.staged.budget', '--require-target'],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert '"build_allowed": false' in result.stdout


def test_recycled_ids_and_historical_high_water():
    from tasks.invsqrt.staged.budget import WirePool
    pool = WirePool()
    pool.set_live({'x': 22, 'scratch': 18})
    assert pool.high_water == 40
    pool.set_live({'x': 22, 'small': 1})
    assert len(pool.live_ids) == 23
    assert pool.high_water == 40
    assert pool.registers['small'] == [22]


def test_rotation_price_increases_when_margin_is_spent():
    from tasks.invsqrt.staged.budget import cost
    full = cost(63, 1553, margin=78847037)
    half = cost(63, 1553, margin=78847037 / 2)
    assert full['c'] == pytest.approx(1867.65435486998)
    assert half['c'] - full['c'] == pytest.approx(44 * 0.56 / 4)
    assert half['ratio'] < full['ratio']
    assert math.isinf(cost(63, 1553, margin=0)['c'])


def test_anf_count_includes_unwritten_ancestors():
    from tasks.invsqrt.staged.budget import anf_cost
    # The only output is abc; the DFS must compute ab even though it is not output.
    assert anf_cost([0, 0, 0, 0, 0, 0, 0, 1]) == 2
    assert anf_cost([0, 1, 1, 0]) == 0  # a XOR b costs only CNOTs.


def test_gate_requires_area_cost_and_supported_schedule():
    from tasks.invsqrt.staged.budget import design_gate
    assert design_gate(63, 18.9, supported=True)
    assert not design_gate(64, 20, supported=True)
    assert not design_gate(63, 18.89, supported=True)
    assert not design_gate(63, 20, supported=False)


def test_optimistic_bound_is_not_a_candidate():
    from tasks.invsqrt.staged.budget import report
    result = report()
    assert not result['build_allowed']
    assert result['staged']['qubits'] == 84
    assert result['optimistic_q63_bound']['c'] > result['target_c_at_63']
    assert result['optimistic_q63_bound']['additional_savings_needed'] > 36
    assert result['binding_stages'] == ['outer forward', 'outer inverse']
