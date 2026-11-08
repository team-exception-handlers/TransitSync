# AI contribution: 50% or more AI-generated
"""US-2.6 #61: strategy selection, current-only actions and audit snapshots."""

from dataclasses import replace

import pytest

from simulator.control.settings import parse_control_settings
from simulator.control.strategies import STRATEGIES
from simulator.control.strategies.rolling_horizon import RollingHorizonStrategy
from tests.simulator.control.rolling_helpers import UniformWalk, group, snapshot, visit
from tests.simulator.control.test_rolling_horizon import planner


def test_only_current_action_is_returned_and_future_is_replanned():
    seen = snapshot(
        (
            visit(),
            visit("B", "P2", 150),
            visit("next", departure=1100),
            visit("next-B", "P2", 1150),
        ),
        (group(), group("P2", 150)),
    )
    strategy = RollingHorizonStrategy(planner(("P1", "P2")))
    actions = strategy.evaluate(seen)
    assert [(a.train_id, a.duration_s) for a in actions] == [("A", 10)]
    later = replace(
        seen,
        time_s=150,
        train_id="B",
        platform_id="P2",
        station_id="S-P2",
        incoming_transfers=(),
    )
    assert strategy.evaluate(later) == ()
    records = strategy.decision_records()
    assert [d["hold_s"] for d in records[0]["plan"]] == [10, 10]
    assert records[1]["chosen_hold_s"] == 0


def test_settings_round_trip_and_registry_preserve_configuration():
    control = parse_control_settings(
        {
            "strategy": "rolling_horizon",
            "rolling_horizon": {"window_s": 120, "max_combinations": 16},
            "hold_search": {"step_s": 10, "max_hold_s": 20},
            "weights": {"w_wait": 1.5},
        }
    )
    saved = control.to_dict()
    assert parse_control_settings(saved) == control
    strategy = STRATEGIES.build(
        control.strategy,
        walking_by_platform={"P1": UniformWalk()},
        rolling_horizon=control.rolling_horizon,
        hold_search=control.hold_search,
        weights=control.weights,
    )
    assert strategy.planner.settings.window_s == 120
    assert strategy.planner.hold_search.candidates() == (0, 10, 20)
    assert strategy.planner.weights.w_wait == 1.5


def test_registry_requires_a_walk_model_instead_of_inventing_one():
    with pytest.raises(ValueError, match="walking_by_platform required"):
        STRATEGIES.build("rolling_horizon")


def test_audit_records_are_detached():
    strategy = RollingHorizonStrategy(planner())
    strategy.evaluate(snapshot())
    records = strategy.decision_records()
    records[0]["plan"].clear()
    assert len(strategy.decision_records()[0]["plan"]) == 1
