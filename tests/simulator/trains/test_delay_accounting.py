# AI contribution: 50% or more AI-generated
"""Hand-calculated delay causes and recovery for holding integration (#48)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.trains.train import ScheduledStop, Train


def vehicle() -> Train:
    """Create a train that can recover 90 seconds of delay at its terminus."""
    return Train(
        "A",
        100,
        (ScheduledStop("S1", "P1", 100, 100), ScheduledStop("S2", "P2", 200, 200)),
        layover_slack=90,
        return_trips=((ScheduledStop("S2", "P3", 400, 400),),),
    )


def mixed_delay() -> Train:
    """Introduce 60 seconds disruption, then 120 seconds of holding."""
    train = vehicle()
    train.update_delay(160, 100)
    train.update_delay(280, 100, hold_delay_s=120)
    return train


def test_hold_is_generated_lateness_but_not_disruption():
    """Hold delay counts as generated delay, but not disruption delay."""
    train = mixed_delay()
    assert train.current_delay == 180
    assert train.generated_delay_s == 180
    assert train.inherited_delay_s == 0
    assert train.disruption_delay_s == 60


@pytest.mark.parametrize(
    ("inherited_wait_s", "generated_s", "inherited_s"),
    [(0, 90, 0), (20, 70, 20), (40, 60, 30)],
    ids=["own_increase_only", "mixed_increase", "entire_increase_inherited"],
)
def test_hold_cause_is_bounded_by_new_lateness_after_inherited_wait(
    inherited_wait_s, generated_s, inherited_s
):
    """An oversized hold value must not change existing disruption delay."""
    train = vehicle()
    train.update_delay(160, 100)
    train.update_delay(190, 100, inherited_wait_s=inherited_wait_s, hold_delay_s=120)

    # Of 30 new seconds: inherited gets 0/20/30, holding gets 30/10/0.
    # Existing disruption stays at 60.
    assert train.current_delay == 90
    assert train.generated_delay_s == generated_s
    assert train.inherited_delay_s == inherited_s
    assert train.disruption_delay_s == 60


def test_ordinary_recovery_reduces_own_causes_proportionally():
    """Recovering half of 120 hold + 60 disruption leaves 60 + 30."""
    train = mixed_delay()
    train.update_delay(190, 100)
    assert train.current_delay == 90
    assert train.generated_delay_s == 90
    assert train.disruption_delay_s == 30


def test_recovery_removes_inherited_lateness_before_own_causes():
    """Recover 30 inherited seconds, then halve hold and disruption delay."""
    train = mixed_delay()
    train.update_delay(310, 100, inherited_wait_s=30)
    train.update_delay(190, 100)
    assert train.inherited_delay_s == 0
    assert train.generated_delay_s == 90
    assert train.disruption_delay_s == 30


def test_terminal_recovery_uses_the_same_cause_allocation():
    """90 seconds of terminal recovery halves hold and disruption delay."""
    train = mixed_delay()
    train.current_stop_index = 1
    # Return arrival 400 + (180 lateness - 90 slack) = 490 seconds.
    assert train.begin_return_trip() == 490
    assert train.current_delay == 90
    assert train.generated_delay_s == 90
    assert train.disruption_delay_s == 30


def test_complete_recovery_does_not_leak_hold_cause_into_future_disruptions():
    """Once recovered, a new 20-second delay is entirely disruption."""
    train = mixed_delay()
    train.update_delay(90, 100)
    assert train.disruption_delay_s == 0
    train.update_delay(120, 100)
    assert train.generated_delay_s == 20
    assert train.disruption_delay_s == 20


def test_arrival_projection_does_not_change_live_delay_accounting():
    """Calculate 30 seconds of arrival disruption without changing the train."""
    train = mixed_delay()
    assert train.disruption_delay_at(190, 100) == 30
    assert train.current_delay == 180
    assert train.generated_delay_s == 180
    assert train.disruption_delay_s == 60


@pytest.mark.parametrize("bad_hold", [-1, float("nan"), float("inf"), True, "30", None])
def test_invalid_hold_cause_is_rejected_without_changing_delay(bad_hold):
    """Invalid hold values raise an error without changing delay."""
    train = mixed_delay()
    with pytest.raises(ValueError, match="finite|Hold delay"):
        train.update_delay(300, 100, hold_delay_s=bad_hold)
    assert train.current_delay == 180
    assert train.disruption_delay_s == 60


@given(
    disruption=st.integers(min_value=0, max_value=10000),
    hold=st.integers(min_value=0, max_value=10000),
    inherited=st.integers(min_value=0, max_value=10000),
    recovery=st.integers(min_value=0, max_value=30000),
)
def test_cause_recovery_preserves_total_lateness(disruption, hold, inherited, recovery):
    """Recovery removes inherited delay first and cannot create more delay."""
    train = vehicle()
    train.update_delay(100 + disruption, 100)
    train.update_delay(100 + disruption + hold, 100, hold_delay_s=hold)
    total = disruption + hold + inherited
    train.update_delay(100 + total, 100, inherited_wait_s=inherited)
    train.update_delay(100 + max(0, total - recovery), 100)
    remaining = max(0, total - recovery)
    assert train.current_delay == remaining
    assert train.generated_delay_s + train.inherited_delay_s == remaining
    assert train.inherited_delay_s == max(0, inherited - recovery)
    assert 0 <= train.disruption_delay_s <= train.generated_delay_s
    assert train.disruption_delay_s <= disruption
