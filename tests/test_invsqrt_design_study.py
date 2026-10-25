"""Study accounting must preserve signed carries and include rotation cost."""

import pytest

from tasks.invsqrt.design_study import carry_step, resource_row


@pytest.mark.parametrize("low,carry,term", [(0, 0, -1), (31, 0, 1), (7, -2, -31), (0, 1, 31)])
def test_signed_carry_preserves_the_integer(low, carry, term):
    new_low, new_carry = carry_step(low, carry, term, width=5)
    assert 0 <= new_low < 32
    assert new_low + 32 * new_carry == low + 32 * carry + term


def test_public_frontier_does_not_transfer_to_our_space_count():
    public = resource_row(82, 1365, 1276.4)
    ours = resource_row(88, 1365, 1276.4)
    assert public["ratio"] == pytest.approx(15.039, abs=.001)
    assert public["clears_gate"]
    assert ours["ratio"] == pytest.approx(14.013, abs=.001)
    assert not ours["clears_gate"]


def test_gate_uses_exact_reference_over_fifteen():
    assert resource_row(1, 2076774 / 15, 0)["clears_gate"]
    assert not resource_row(1, 138452, 0)["clears_gate"]
