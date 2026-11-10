# AI contribution: 50% or more AI-generated
"""US-2.6 #61: enumerate complete windows and choose deterministic plans."""

from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulator.control.hold_search import HoldInputs, HoldSearch, HoldSearchSettings
from simulator.control.planning import RollingHorizonSettings
from simulator.control.rolling_horizon import RollingHorizonPlanner
from tests.simulator.control.rolling_helpers import UniformWalk, group, snapshot, visit


def planner(platforms=("P1",), window=100, budget=100000):
    return RollingHorizonPlanner(
        dict.fromkeys(platforms, UniformWalk()),
        RollingHorizonSettings(window, budget),
        HoldSearchSettings(10, 10),
    )


def test_every_station_including_window_end_is_evaluated():
    visits = tuple(
        visit(train, platform, time)
        for train, platform, time in [
            ("A", "P1", 100),
            ("B", "P2", 150),
            ("C", "P3", 200),
        ]
    )
    followers = tuple(
        visit(f"next-{v.train_id}", v.platform_id, v.departure_s + 1000) for v in visits
    )
    seen = snapshot(
        (*visits, *followers), [group(v.platform_id, v.departure_s) for v in visits]
    )
    result = planner(("P1", "P2", "P3")).plan(seen)
    assert [d.visit.station_id for d in result.decisions] == ["S-P1", "S-P2", "S-P3"]
    assert [d.hold_s for d in result.decisions] == [10, 10, 10]
    assert result.combinations_evaluated == 8
    # Each hold catches 10 * .1 = 1; 1 * 1000 * 2 - 10 * 10 = 1900 pax-s.
    assert result.net_ps == 5700


def test_visit_just_outside_window_is_not_a_decision():
    seen = snapshot((visit(), visit("B", "P2", 200.0001)))
    assert len(planner().plan(seen).decisions) == 1


def test_single_station_matches_existing_hold_search():
    seen = snapshot()
    search = HoldSearch(UniformWalk(), settings=HoldSearchSettings(10, 10))
    local = search.run(HoldInputs.from_observation(seen, 1000))
    result = planner().plan(seen)
    assert result.hold_s == local.hold_s
    assert result.net_ps == local.chosen.net_ps


def test_equal_benefit_and_cost_prefers_zero_hold():
    assert planner().plan(snapshot(load=200)).hold_s == 0


def test_conflicting_departures_are_projected_before_valuing_connections():
    seen = snapshot((visit(), visit("B", departure=105), visit("next", departure=1100)))
    result = planner().plan(seen)
    # Separation moves B's baseline departure to 190. Each catches one:
    # (1 * 90 * 2 - 100) + (1 * 910 * 2 - 100) = 1800 pax-s.
    assert [d.hold_s for d in result.decisions] == [10, 10]
    # CDF subtraction incurs round-off well below a millionth of a pax-s.
    assert result.net_ps == pytest.approx(1800, abs=1e-6)


def test_missing_forecast_fails_clearly():
    seen = replace(snapshot(), future_visits=())
    with pytest.raises(ValueError, match="deciding train's future visit"):
        planner().plan(seen)


def test_exact_search_budget_does_not_silently_drop_stations():
    seen = snapshot()
    policy = planner(budget=1)
    with pytest.raises(ValueError, match="2 combinations"):
        policy.plan(seen)


@given(st.integers(0, 500), st.integers(0, 100))
@settings(max_examples=25)
def test_identical_inputs_are_deterministic_and_never_mutated(load, size):
    seen = snapshot(groups=(group(count=size),), load=load)
    policy = planner()
    first = policy.plan(seen)
    second = policy.plan(seen)
    assert first == second
    assert first.hold_s in (0, 10)
    assert seen.trains[0].onboard_load == load
