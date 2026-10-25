# AI contribution: 50% or more AI-generated
"""Delay injection integration tests for US-1.5 #26."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from simulator.disruptions import get_disruption_preset
from simulator.engine.event_queue import Scheduler
from simulator.engine.events import TrainArrival
from simulator.engine.runner import run_scenario
from simulator.network import build_network
from simulator.network_config import load_network
from simulator.trains.disruption import DelayInjection
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent
from simulator.trains.train_generator import generate_from_headway


def _train(train_id: str, platform_b: str = "P-B") -> Train:
    return Train(
        id=train_id,
        capacity=100,
        schedule=(
            ScheduledStop("A", "P-A-" + train_id, 0, 0),
            ScheduledStop("B", platform_b, 100, 100),
            ScheduledStop("C", "P-C-" + train_id, 200, 200),
        ),
    )


def test_delay_targets_location_and_propagates_into_later_train_movement(
    tmp_path, minimal_scenario
):
    scenario = replace(minimal_scenario, name="delay-test", description="Delay test.")
    disruption = DelayInjection(
        disruption_id="delay-target",
        time_s=100,
        delay_s=40,
        train_id="target",
        station_id="B",
        platform_id="P-B",
    )

    def build_components(_scenario, _streams):
        return [
            TrainComponent(
                [_train("target"), _train("other")],
                minimum_gap_s=10,
                delay_injections=[disruption],
            )
        ]

    result = run_scenario(scenario, int, build_components, tmp_path)
    arrivals = [
        json.loads(line)
        for line in result.events_path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["event_type"] == "train_arrival"
    ]
    arrivals_by_train = {
        (record["train_id"], record["platform_id"]): record for record in arrivals
    }

    assert arrivals_by_train[("target", "P-B")]["time_s"] == 150
    assert arrivals_by_train[("target", "P-B")]["disruption_delay_s"] == 40
    assert arrivals_by_train[("other", "P-B")]["time_s"] == 100
    assert arrivals_by_train[("other", "P-B")]["disruption_delay_s"] == 0
    assert arrivals_by_train[("target", "P-C-target")]["time_s"] == 250

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["scenario_name"] == "delay-test"
    assert manifest["scenario_description"] == "Delay test."
    assert manifest["disruptions"] == [
        {
            "id": "delay-target",
            "type": "delay",
            "time_s": 100.0,
            "delay_s": 40.0,
            "train_id": "target",
            "station_id": "B",
            "platform_id": "P-B",
            "applied": True,
            "trigger_time_s": 110,
            "arrival_time_s": 150,
        }
    ]


def test_named_delay_preset_runs_and_writes_a_reproducible_manifest(
    tmp_path, minimal_scenario
):
    preset = get_disruption_preset("mcgill_platform_delay")
    scenario = replace(
        minimal_scenario, name=preset.name, description=preset.description
    )

    def build_components(_scenario, _streams):
        trains = generate_from_headway(
            start_s=0,
            end_s=0,
            headway_s=300,
            route=(
                ScheduledStop("origin", "P-origin", 0, 0),
                ScheduledStop("mcgill", "rem_mcgill_0", 120, 120),
                ScheduledStop("next", "P-next", 220, 220),
            ),
            capacity=100,
            line_id="rem",
        )
        return [TrainComponent(trains, delay_injections=preset.delay_injections)]

    first = run_scenario(scenario, int, build_components, tmp_path / "first")
    second = run_scenario(scenario, int, build_components, tmp_path / "second")
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    records = [json.loads(line) for line in first.events_path.read_text().splitlines()]
    mcgill_arrival = next(
        record
        for record in records
        if record["event_type"] == "train_arrival"
        and record["platform_id"] == "rem_mcgill_0"
    )

    assert mcgill_arrival["time_s"] == 180
    assert mcgill_arrival["train_id"] == "rem_0001"
    assert mcgill_arrival["disruption_delay_s"] == 60
    assert manifest["scenario_name"] == preset.name
    assert manifest["disruptions"][0]["applied"] is True
    second_manifest = json.loads(second.manifest_path.read_text(encoding="utf-8"))
    manifest.pop("timestamp")
    second_manifest.pop("timestamp")
    assert manifest == second_manifest


def test_named_delay_preset_matches_saved_network_and_only_target_direction(
    tmp_path, minimal_scenario
):
    config_path = (
        Path(__file__).resolve().parents[3] / "config/reference_network/network.json"
    )
    network = build_network(load_network(config_path))
    preset = get_disruption_preset("mcgill_platform_delay")
    target = network.platforms[preset.delay_injections[0].platform_id]
    assert (target.interchange_id, target.line_id, target.direction_id) == (
        "mcgill",
        "rem",
        0,
    )

    def build_components(_scenario, _streams):
        trains = []
        for direction in (0, 1):
            platform = network.platforms[f"rem_mcgill_{direction}"]
            trains.append(
                Train(
                    id=f"rem-direction-{direction}",
                    capacity=100,
                    line_id=platform.line_id,
                    schedule=(
                        ScheduledStop(
                            platform.interchange_id, platform.platform_id, 120, 120
                        ),
                    ),
                )
            )
        return [TrainComponent(trains, delay_injections=preset.delay_injections)]

    result = run_scenario(minimal_scenario, int, build_components, tmp_path)
    records = [json.loads(line) for line in result.events_path.read_text().splitlines()]
    arrivals = {
        record["platform_id"]: record
        for record in records
        if record["event_type"] == "train_arrival"
    }
    assert arrivals["rem_mcgill_0"]["time_s"] == 180
    assert arrivals["rem_mcgill_0"]["disruption_delay_s"] == 60
    assert arrivals["rem_mcgill_1"]["time_s"] == 120
    assert arrivals["rem_mcgill_1"]["disruption_delay_s"] == 0
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["disruptions"][0]["platform_id"] == "rem_mcgill_0"
    assert manifest["disruptions"][0]["applied"] is True


def test_unprocessed_future_arrival_is_not_reported_as_an_applied_disruption(
    tmp_path, minimal_scenario
):
    scenario = replace(minimal_scenario, duration_s=50)
    disruption = DelayInjection(
        disruption_id="future-delay",
        time_s=100,
        delay_s=40,
        train_id="target",
        platform_id="P-B",
    )

    def build_components(_scenario, _streams):
        return [TrainComponent([_train("target")], delay_injections=[disruption])]

    result = run_scenario(scenario, int, build_components, tmp_path)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert result.summary.events_pending == 1
    assert manifest["disruptions"][0]["applied"] is False
    assert manifest["disruptions"][0]["trigger_time_s"] is None
    assert manifest["disruptions"][0]["arrival_time_s"] is None


def test_disruption_time_uses_the_safe_arrival_after_minimum_gap(
    tmp_path, minimal_scenario
):
    disruption = DelayInjection(
        disruption_id="gap-delayed-disruption",
        time_s=150,
        delay_s=40,
        train_id="target",
        platform_id="P-B",
    )

    def build_components(_scenario, _streams):
        leader = Train(
            id="leader",
            capacity=100,
            schedule=(
                ScheduledStop("A", "P-A-leader", 0, 0),
                ScheduledStop("B", "P-B", 100, 100),
            ),
        )
        target = Train(
            id="target",
            capacity=100,
            schedule=(
                ScheduledStop("A", "P-A-target", 0, 0),
                ScheduledStop("B", "P-B", 110, 110),
            ),
        )
        return [
            TrainComponent(
                [leader, target],
                minimum_gap_s=90,
                delay_injections=[disruption],
            )
        ]

    result = run_scenario(minimal_scenario, int, build_components, tmp_path)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    record = manifest["disruptions"][0]
    assert record["applied"] is True
    assert record["trigger_time_s"] == 190
    assert record["arrival_time_s"] == 230


@pytest.mark.parametrize(("delay_s", "expected_arrival_s"), [(15, 115), (75, 175)])
def test_delay_magnitude_is_independent_of_target_location(delay_s, expected_arrival_s):
    disruption = DelayInjection(
        disruption_id="independent-magnitude",
        time_s=100,
        delay_s=delay_s,
        platform_id="P-B",
    )
    component = TrainComponent([_train("target")], delay_injections=[disruption])
    scheduler = Scheduler()
    component.start(scheduler)
    arrivals: list[TrainArrival] = []

    def process(event):
        if isinstance(event, TrainArrival):
            arrivals.append(event)
        component.handle(event, scheduler)

    scheduler.run_until(300, process)
    target_arrival = next(event for event in arrivals if event.platform_id == "P-B")
    assert target_arrival.time_s == expected_arrival_s


def test_delay_location_is_independent_of_magnitude():
    disruption = DelayInjection(
        disruption_id="independent-location",
        time_s=100,
        delay_s=40,
        platform_id="P-B",
    )
    component = TrainComponent(
        [_train("target", platform_b="P-OTHER")], delay_injections=[disruption]
    )
    scheduler = Scheduler()
    component.start(scheduler)
    arrivals: list[TrainArrival] = []

    def process(event):
        if isinstance(event, TrainArrival):
            arrivals.append(event)
        component.handle(event, scheduler)

    scheduler.run_until(300, process)
    target_arrival = next(event for event in arrivals if event.platform_id == "P-OTHER")
    assert target_arrival.time_s == 100
    assert component.manifest_entries()[0]["applied"] is False


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("disruption_id", "", "Disruption ID"),
        ("time_s", float("nan"), "time_s"),
        ("time_s", -1, "time_s"),
        ("delay_s", 0, "delay_s"),
        ("delay_s", float("inf"), "delay_s"),
        ("platform_id", "", "platform ID"),
    ],
)
def test_invalid_delay_disruption_is_rejected(field, value, message):
    values = {
        "disruption_id": "invalid-test",
        "time_s": 100,
        "delay_s": 30,
        "platform_id": "P-B",
    }
    values[field] = value
    with pytest.raises(ValueError, match=message):
        DelayInjection(**values)
