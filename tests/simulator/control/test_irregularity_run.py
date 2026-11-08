# AI contribution: 50% or more AI-generated
"""Exercise Issue #63 through real departures, snapshots and control decisions."""

import json
from unittest.mock import Mock

import pytest

from simulator.control.decision import DecisionPipeline
from simulator.control.strategies import STRATEGIES
from simulator.control.strategies.no_control import NoControlStrategy
from simulator.engine.random_streams import StreamManager
from simulator.engine.runner import run_scenario
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent
from tests.simulator.control.headway_run_helpers import (
    load,
    run_selected,
    scenario_input,
)


def run_with_observations(output_dir, config, trains):
    """Run fresh trains with the scenario's policy and capture its snapshots."""
    scenario = load(config)
    strategy = Mock(
        wraps=STRATEGIES.build(
            scenario.control.strategy,
            target_headways_s=scenario.control.target_headways_s,
        ),
        spec=["evaluate", "name"],
    )
    result = run_scenario(
        scenario,
        StreamManager,
        lambda settings, _: [
            TrainComponent(
                trains,
                minimum_gap_s=60,
                decision=DecisionPipeline(strategy),
                control=settings.control,
            )
        ],
        output_dir,
    )
    observations = [call.args[0] for call in strategy.evaluate.call_args_list]
    events = [json.loads(line) for line in result.events_path.read_text().splitlines()]
    return result, observations, events


def disrupted_trains():
    """Schedule regular 60-second gaps with a lasting 30-second phase shift."""
    trains = []
    for index in range(7):
        scheduled_s = 100 + 60 * index
        delay_s = 30 if index >= 2 else 0
        trains.append(
            Train(
                f"train-{index}",
                800,
                (ScheduledStop("station", "P", scheduled_s - 10, scheduled_s),),
                current_delay=delay_s,
                generated_delay_s=delay_s,
            )
        )
    return trains


def test_no_control_observes_completed_headways_and_recovers(tmp_path):
    config = scenario_input("no_control")
    config["control"]["irregularity_window_size"] = 3
    result, observations, events = run_with_observations(
        tmp_path, config, disrupted_trains()
    )
    # Departures have gaps 60, 90, then four 60s. Each decision sees only
    # previously completed gaps, so the 90-second gap appears one train later.
    values = [item.service_irregularity for item in observations]
    assert values[:3] == [None, None, 0.0]
    assert values[3:] == pytest.approx([1 / 4, 1 / 6, 1 / 6, 0])
    departures = [event for event in events if event["event_type"] == "train_departure"]
    assert [event["time_s"] for event in departures] == [
        100,
        160,
        250,
        310,
        370,
        430,
        490,
    ]
    assert [event["event_type"] for event in events] == [
        "train_arrival",
        "departure_due",
        "train_departure",
    ] * 7
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["control"]["irregularity_window_size"] == 3


def test_same_seed_restarts_history_and_reproduces_run(tmp_path):
    config = scenario_input("no_control")
    first, first_snapshots, _ = run_with_observations(
        tmp_path / "first", config, disrupted_trains()
    )
    second, second_snapshots, _ = run_with_observations(
        tmp_path / "second", config, disrupted_trains()
    )
    assert first_snapshots[0].service_irregularity is None
    assert second_snapshots[0].service_irregularity is None
    assert first_snapshots == second_snapshots
    assert first.events_path.read_bytes() == second.events_path.read_bytes()
    assert first.summary_path.read_bytes() == second.summary_path.read_bytes()


def test_configured_target_and_actual_held_departure_reach_strategy(tmp_path):
    config = scenario_input("headway_regulation", target=90)
    trains = [
        Train(f"train-{index}", 800, (ScheduledStop("station", "P", t - 10, t),))
        for index, t in enumerate([100, 160, 310])
    ]
    _, observations, events = run_with_observations(tmp_path, config, trains)
    # Headway regulation holds the second train from 160 to 190. At 310 the
    # completed gap matches the 90-second configured target, despite a
    # 60-second timetable gap and readiness at 160.
    departures = [event for event in events if event["event_type"] == "train_departure"]
    assert [event["time_s"] for event in departures] == [100, 190, 310]
    assert [item.service_irregularity for item in observations] == [None, None, 0.0]


def test_shared_factory_applies_irregularity_window(tmp_path, monkeypatch):
    config = scenario_input("no_control")
    config["control"]["irregularity_window_size"] = 1
    observed = []
    original_evaluate = NoControlStrategy.evaluate

    def record_observation(self, observation):
        observed.append(observation.service_irregularity)
        return original_evaluate(self, observation)

    monkeypatch.setattr(NoControlStrategy, "evaluate", record_observation)
    result = run_selected(tmp_path, config, engine_gap=60, trains=disrupted_trains())

    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["control"]["irregularity_window_size"] == 1
    assert observed == [None, None, 0.0, 0.5, 0.0, 0.0, 0.0]
