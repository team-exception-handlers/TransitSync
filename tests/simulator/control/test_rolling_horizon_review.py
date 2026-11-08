# AI contribution: 50% or more AI-generated
"""PR #198: active visit identity and bounded all-station search."""

from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from simulator.control.hold_search import HoldSearchSettings
from simulator.control.planning import RollingHorizonSettings
from simulator.control.rolling_horizon import RollingHorizonPlanner
from tests.simulator.control.rolling_helpers import UniformWalk, group, snapshot, visit


def independent_stations(count):
    """One decision and later headway reference at each independent station."""
    points = tuple(
        visit("A" if i == 0 else f"train-{i}", f"P{i + 1}", 100 + 10 * i)
        for i in range(count)
    )
    later = tuple(
        visit(f"next-{i}", point.platform_id, point.departure_s + 1000)
        for i, point in enumerate(points)
    )
    seen = snapshot(
        (*points, *later),
        tuple(group(p.platform_id, p.departure_s) for p in points),
    )
    walking = dict.fromkeys((p.platform_id for p in points), UniformWalk())
    return seen, walking


def test_repeated_platform_selects_arrived_visit_regardless_of_collection_order():
    current = replace(visit("A", "P1", 100, trip=1), arrived=True)
    later = visit("A", "P1", 300, trip=2)
    seen = snapshot((later, current), groups=())
    policy = RollingHorizonPlanner({}, hold_search=HoldSearchSettings(10, 10))
    original = policy.plan(seen)
    reversed_result = policy.plan(replace(seen, future_visits=(current, later)))
    assert original.decisions[0].visit.key == ("A", 1, 0)
    assert original == reversed_result


def test_single_current_candidate_without_arrived_marker_remains_supported():
    seen = snapshot((visit(),), groups=())
    seen = replace(seen, future_visits=(replace(seen.future_visits[0], arrived=False),))
    result = RollingHorizonPlanner({}).plan(seen)
    assert result.decisions[0].visit.key == ("A", 0, 0)


def test_repeated_platform_without_active_marker_fails_instead_of_guessing():
    seen = snapshot((visit(trip=1), visit(departure=300, trip=2)), groups=())
    policy = RollingHorizonPlanner({})
    with pytest.raises(ValueError, match="deciding train's future visit"):
        policy.plan(seen)


@pytest.mark.parametrize("count", [7, 15])
def test_default_grid_handles_large_windows_without_dropping_stations(count):
    seen, walking = independent_stations(count)
    before = deepcopy(seen)
    result = RollingHorizonPlanner(walking).plan(seen)
    assert len(result.decisions) == count
    assert {p.visit.platform_id for p in result.decisions} == set(walking)
    assert result.exact is False
    assert result.total_combinations == 13**count
    assert result.combinations_evaluated <= 100_000
    # Independent stations make the full 60 s hold optimal at every point:
    # 6 caught * 1000 s * 2 - 10 onboard * 60 s = 11400 pax-s each.
    assert [p.hold_s for p in result.decisions] == [60] * count
    assert result.net_ps == 11400 * count
    assert seen == before
    assert all(alt["exact"] is False for alt in asdict(result)["alternatives"])


def test_four_default_grid_points_use_bounded_search_instead_of_28561_forecasts():
    seen, walking = independent_stations(4)
    result = RollingHorizonPlanner(walking).plan(seen)
    assert result.exact is False
    assert result.total_combinations == 28_561
    assert result.combinations_evaluated < 2000
    assert result.net_ps == 45_600


def test_small_search_remains_exact_with_complete_alternatives():
    seen, walking = independent_stations(3)
    result = RollingHorizonPlanner(walking).plan(seen)
    assert result.exact is True
    assert result.combinations_evaluated == 13**3
    assert len(result.alternatives) == 13
    assert result.net_ps == 34_200


def test_approximation_is_deterministic_and_respects_tight_budget():
    seen, walking = independent_stations(7)
    policy = RollingHorizonPlanner(
        walking, RollingHorizonSettings(max_combinations=100)
    )
    first = policy.plan(seen)
    second = policy.plan(
        replace(seen, future_visits=tuple(reversed(seen.future_visits)))
    )
    assert first == second
    assert first.exact is False
    assert first.combinations_evaluated <= 100
    assert len(first.decisions) == 7
    assert len(first.alternatives) == 13
    assert first.net_ps >= 0


def test_budget_too_small_to_explore_each_station_fails_before_scoring(monkeypatch):
    seen, walking = independent_stations(7)
    policy = RollingHorizonPlanner(walking, RollingHorizonSettings(max_combinations=84))

    def unexpected(*args):
        pytest.fail("candidate scoring started before validating the budget")

    monkeypatch.setattr(RollingHorizonPlanner, "_evaluate_plan", unexpected)
    with pytest.raises(ValueError, match="85 combinations"):
        policy.plan(seen)


def test_minimum_budget_scores_every_duration_at_every_station(monkeypatch):
    seen, walking = independent_stations(7)
    policy = RollingHorizonPlanner(walking, RollingHorizonSettings(max_combinations=85))
    calls = []
    original = RollingHorizonPlanner._evaluate_plan

    def record(self, decisions, *args):
        calls.append(tuple(d.hold_s for d in decisions))
        return original(self, decisions, *args)

    monkeypatch.setattr(RollingHorizonPlanner, "_evaluate_plan", record)
    result = policy.plan(seen)
    assert result.combinations_evaluated == 85
    assert len(calls) == 85
    for index in range(7):
        assert {values[index] for values in calls} == set(
            policy.hold_search.candidates()
        )


@pytest.mark.parametrize("trains", [3, 8])
def test_connected_ten_stop_line_can_plan_with_default_budget(trains):
    visits = tuple(
        visit(
            "A" if train == 0 else f"train-{train}",
            f"P{stop + 1}",
            100 + 100 * train + 100 * stop,
            index=stop,
        )
        for train in range(trains)
        for stop in range(10)
    )
    result = RollingHorizonPlanner({}).plan(snapshot(visits, groups=()))
    assert result.exact is False
    assert result.total_combinations > 100_000
    assert result.combinations_evaluated <= 100_000
    assert len(result.decisions) >= 7
    assert result.net_ps == 0
    assert all(d.hold_s == 0 for d in result.decisions)
