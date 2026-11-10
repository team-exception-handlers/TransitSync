# AI contribution: 50% or more AI-generated
"""US-2.6 #62: verify marginal costs and movement projection by hand."""

from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulator.control.downstream import project_visits
from simulator.control.interface import PlatformState
from simulator.trains.suspension import LineSuspension
from tests.simulator.control.downstream_helpers import cascade, forecast
from tests.simulator.control.rolling_helpers import snapshot, visit


def test_delay_propagates_recursively_across_three_stations():
    baseline, candidate, _ = forecast(cascade())
    # A holds 10 at P1. B must follow A's departures by at least 90 seconds.
    assert [p.departure_s for p in baseline] == [100, 210, 310, 190, 300, 400]
    assert [p.departure_s for p in candidate] == [110, 220, 320, 200, 310, 410]


def test_onboard_delay_is_not_counted_again_at_every_station():
    _, _, cost = forecast(cascade())
    # B's 100 riders acquire 10 seconds once: 1000 pax-s.
    # A's own 10 * 10 is already in the local cost and must not reappear here.
    assert cost.onboard_ps == 1000
    assert cost.waiting_ps == 0


def test_waiting_cost_is_charged_once_per_platform_queue():
    seen = replace(
        cascade(),
        platforms=(PlatformState("P2", 20, None), PlatformState("P3", 30, None)),
    )
    _, _, cost = forecast(seen)
    # First service A is delayed 10 s at each platform: (20+30)*10*2 = 1000.
    # B also serves them, but must not charge the same waiting people again.
    assert cost.waiting_ps == 1000
    assert cost.total_ps == 2000


def test_zero_hold_has_zero_marginal_cost_despite_existing_congestion():
    baseline, candidate, cost = forecast(cascade(), hold=0)
    assert baseline == candidate
    assert cost.total_ps == 0


def test_occupancy_prevents_a_follower_arriving_before_the_held_train_leaves():
    seen = replace(snapshot((visit(), visit("B", departure=115))), minimum_gap_s=1)
    _, candidate, _ = forecast(seen, hold=20)
    assert candidate[1].arrival_s > candidate[0].departure_s
    assert candidate[1].departure_s == pytest.approx(130, abs=1e-9)


def test_known_departure_boundary_uses_the_engine_gap():
    seen = replace(
        snapshot(), platforms=(PlatformState("P1", 0, 50),), minimum_gap_s=90
    )
    baseline, _, _ = forecast(seen, hold=0)
    assert baseline[0].departure_s == 140


def test_terminal_slack_absorbs_added_delay_once():
    terminal = replace(
        visit("A", "T", 210, index=1),
        departure_s=200,
        skips_departure=True,
        can_hold=False,
    )
    returning = replace(visit("A", "R", 310, trip=1), recovery_s=5)
    seen = snapshot(
        (visit(), terminal, returning, visit("A", "R2", 410, trip=1, index=1))
    )
    _, candidate, cost = forecast(seen)
    assert [p.arrival_s for p in candidate] == [90, 210, 305, 405]
    assert [p.departure_s for p in candidate] == [110, 210, 315, 415]
    assert cost.total_ps == 0


def test_dispatch_suspension_crossing_adds_real_delay_cost():
    seen = replace(snapshot(), suspensions=(LineSuspension("line", 105, 200),))
    _, candidate, cost = forecast(seen)
    # Ten seconds of holding crosses the dispatch closure: depart at 200,
    # not 110. The 90 additional seconds cost 10 * 90 * 1 = 900 pax-s.
    assert candidate[0].departure_s == 200
    assert cost.onboard_ps == 900


def test_delay_cost_is_limited_to_the_forward_window():
    seen = replace(cascade(), platforms=(PlatformState("P2", 20, None),))
    _, _, cost = forecast(seen, end=215)
    # A's P2 service waits only five seconds inside this window: 20*5*2.
    # B acquired 10 s at P1 before the cutoff; no further cost is added at P2.
    assert cost.waiting_ps == 200
    assert cost.onboard_ps == 1000


def test_missing_downstream_passenger_information_contributes_zero():
    seen = snapshot((visit(),), groups=())
    _, _, cost = forecast(replace(seen, trains=(), platforms=()))
    assert cost.total_ps == 0


@given(st.integers(0, 60))
@settings(max_examples=25)
def test_projection_is_deterministic_and_never_reduces_departure_time(hold):
    seen = cascade()
    baseline, candidate, cost = forecast(seen, hold=hold)
    _, repeated, repeated_cost = forecast(seen, hold=hold)
    assert repeated == candidate
    assert cost == repeated_cost
    assert cost.total_ps >= 0
    for base, proposed in zip(baseline, candidate, strict=True):
        assert proposed.departure_s >= base.departure_s
    for platform in ("P1", "P2", "P3"):
        services = sorted(
            (p for p in candidate if p.visit.platform_id == platform),
            key=lambda p: p.arrival_s,
        )
        assert services[1].arrival_s - services[0].arrival_s >= seen.minimum_gap_s
        assert services[1].departure_s - services[0].departure_s >= seen.minimum_gap_s
        assert services[1].arrival_s > services[0].departure_s


def test_invalid_duplicate_forecast_visits_are_rejected():
    seen = snapshot((visit(), visit()))
    with pytest.raises(ValueError, match="keys must be unique"):
        project_visits(seen, {}, 1000)


@pytest.mark.parametrize("seconds", [-1, float("inf"), float("nan"), True])
def test_projection_rejects_invalid_hold_seconds(seconds):
    seen = cascade()
    holds = {("A", 0, 0): seconds}
    with pytest.raises(ValueError, match="projected hold_s"):
        project_visits(seen, holds, 1000)


def test_future_decision_pushed_past_window_is_replanned_later():
    seen = cascade()
    # B would be ready at 190; A's 100-second hold delays its arrival until
    # just after 200, so its dwell cannot end within this 195-second window.
    projected = project_visits(seen, {("A", 0, 0): 100, ("B", 0, 0): 10}, 195)
    later = next(p for p in projected if p.visit.train_id == "B")
    assert later.due_s > 195
    assert later.hold_s == 0


def test_full_first_service_does_not_charge_the_waiting_queue():
    seen = replace(
        snapshot((visit(),), load=800), platforms=(PlatformState("P1", 20, None),)
    )
    _, _, cost = forecast(seen)
    assert cost.waiting_ps == 0
