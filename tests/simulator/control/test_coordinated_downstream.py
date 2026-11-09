# AI contribution: 50% or more AI-generated
"""US-2.6 #61/#62: optimize joint holds against downstream consequences."""

from dataclasses import replace

import pytest

from simulator.control.hold_search import HoldInputs, HoldSearch, HoldSearchSettings
from simulator.control.planning import RollingHorizonSettings
from simulator.control.rolling_horizon import RollingHorizonPlanner
from tests.simulator.control.downstream_helpers import (
    cascade,
    forecast,
    harmful_snapshot,
)
from tests.simulator.control.rolling_helpers import UniformWalk, group, snapshot, visit


def test_locally_favourable_but_globally_harmful_hold_is_rejected():
    seen = harmful_snapshot()
    grid = HoldSearchSettings(10, 10)
    local = HoldSearch(UniformWalk(), settings=grid).run(
        HoldInputs.from_observation(seen, 200)
    )
    assert local.hold_s == 10
    # One caught rider * 200 s * 2 - 10 onboard * 10 s = +300 locally.
    assert local.chosen.net_ps == 300
    baseline, candidate, cost = forecast(seen, end=700)
    assert candidate[-1].departure_s - baseline[-1].departure_s == pytest.approx(
        10, abs=1e-9
    )
    assert cost.total_ps == pytest.approx(5000, abs=1e-6)
    planner = RollingHorizonPlanner(
        {"P1": UniformWalk()}, RollingHorizonSettings(600), grid
    )
    assert planner.plan(seen).hold_s == 0


def test_shorter_safe_hold_wins_over_longer_harmful_alternative():
    # A has a 5-second margin at P2 before it delays the heavily loaded B.
    seen = harmful_snapshot()
    visits = tuple(
        replace(
            v,
            arrival_s=v.arrival_s + 5,
            departure_s=v.departure_s + 5,
            scheduled_arrival_s=v.scheduled_arrival_s + 5,
            scheduled_departure_s=v.scheduled_departure_s + 5,
        )
        if v.train_id == "B" and v.platform_id == "P2"
        else v
        for v in seen.future_visits
    )
    planner = RollingHorizonPlanner(
        {"P1": UniformWalk()}, RollingHorizonSettings(600), HoldSearchSettings(5, 10)
    )
    result = planner.plan(replace(seen, future_visits=visits))
    assert result.hold_s == 5
    assert result.net_ps == pytest.approx(150, abs=1e-6)


def test_forecast_does_not_depend_on_snapshot_collection_order():
    seen = cascade()
    planner = RollingHorizonPlanner(
        {"P1": UniformWalk()}, RollingHorizonSettings(600), HoldSearchSettings(10, 10)
    )
    original = planner.plan(seen)
    reordered = planner.plan(
        replace(
            seen,
            future_visits=tuple(reversed(seen.future_visits)),
            trains=tuple(reversed(seen.trains)),
        )
    )
    assert original == reordered


def test_upstream_station_without_local_transfers_is_still_enumerated():
    class FixedWalk:
        def cdf(self, t_s):
            return float(t_s >= 130)

    # A walking group released at 100 reaches P2 at 230. Holding only at P2
    # can extend 210 to 220, missing it. Ten seconds at BOTH stations catches
    # the group: 1*1000*2 - 10*(10+10) = 1800 passenger-seconds.
    seen = snapshot(
        (visit(), visit("A", "P2", 210, index=1), visit("next", "P2", 1210)),
        (group("P2", 100, count=1),),
    )
    policy = RollingHorizonPlanner(
        {"P2": FixedWalk()}, RollingHorizonSettings(200), HoldSearchSettings(10, 10)
    )
    result = policy.plan(seen)
    assert result.combinations_evaluated == 4
    assert [d.hold_s for d in result.decisions] == [10, 10]
    assert result.net_ps == 1800
