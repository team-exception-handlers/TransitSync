# AI contribution: 50% or more AI-generated
"""Run saved headway selections through the train engine (#48).

A leaves at 200; B is scheduled and ready at 400.
Headway holds B; schedule-based control does not.
The event and manifest checks must agree.

The runs use the same arrivals and dwell times.
B starts on time, so its hold creates lateness.
A second target checks that saved values affect the hold.
"""

import json
from datetime import date

import pytest

from simulator.control.decision import DecisionPipeline
from simulator.control.headway_configuration import validate_headway_configuration
from simulator.control.rules import OperatingRulesEnforcer
from simulator.control.strategies import STRATEGIES
from simulator.engine.random_streams import StreamManager
from simulator.engine.runner import run_scenario
from simulator.scenario import (
    DatasetMetadata,
    ScenarioValidationError,
    load_scenario_json,
)
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


def scenario_input(strategy="headway_regulation", target=300, scenario_gap=60):
    """Build fresh scenario values with a fixed date and seed.

    Nondefault search settings expose values lost when saving or loading.
    Their 90-second cap does not apply to headway holds.
    """
    control = {
        "strategy": strategy,
        "hold_search": {"step_s": 10, "max_hold_s": 90},
        "weights": {"w_wait": 1.5, "w_onboard": 0.75},
    }
    if strategy == "headway_regulation":
        control["target_headways_s"] = {"P": target}
    return {
        "dataset_id": "test",
        "date": "2026-10-05",
        "start_time": "07:00",
        "duration_s": 600,
        "master_seed": 7,
        "interchanges": ["mcgill"],
        "control": control,
        "operating_rules": {"min_safe_gap": scenario_gap, "max_hold_time": 300},
    }


def load(values):
    """Load a scenario using local test dataset metadata.

    A fixed service date keeps coverage checks repeatable.
    """
    dataset = DatasetMetadata(
        "test",
        date(2026, 10, 5),
        date(2026, 10, 5),
        {"mcgill": 86400},
        frozenset({"mcgill"}),
    )
    return load_scenario_json(json.dumps(values), {"test": dataset})


def run_selected(output_dir, values, *, engine_gap=90, trains=None, catalog=None):
    """Run the saved policy with one gap for validation and movement.

    The factory builds the strategy from loaded scenario settings.
    Optional trains and platform IDs test complete-trip validation.
    Check settings before any component starts.
    Create a fresh strategy on every call.
    """
    scenario = load(values)
    if trains is None:
        trains = [
            Train("A", 800, (ScheduledStop("S", "P", 170, 200),)),
            Train("B", 800, (ScheduledStop("S", "P", 370, 400),)),
        ]
    if catalog is None:
        catalog = {"P"}

    def build_components(settings, _streams):
        validate_headway_configuration(settings.control, trains, catalog, engine_gap)
        policy = STRATEGIES.build(
            settings.control.strategy,
            target_headways_s=settings.control.target_headways_s,
        )
        return [
            TrainComponent(
                trains,
                minimum_gap_s=engine_gap,
                decision=DecisionPipeline(
                    policy, enforcer=OperatingRulesEnforcer(settings.operating_rules)
                ),
            )
        ]

    return run_scenario(scenario, StreamManager, build_components, output_dir)


def event_tuples(records, event_type, fields):
    """Collect every matching event, including duplicates.

    Keep log order so tests can catch events in the wrong order.
    """
    return [
        tuple(record[field] for field in fields)
        for record in records
        if record["event_type"] == event_type
    ]


@pytest.mark.parametrize(
    ("strategy", "target", "departure", "hold"),
    [
        ("headway_regulation", 300, 500, 100),
        ("headway_regulation", 250, 450, 50),
        ("schedule_based", None, 400, 0),
    ],
)
def test_saved_selection_controls_actual_events(
    tmp_path, strategy, target, departure, hold
):
    """Check exact movements, holds and delay causes.

    Both targets produce different departures from schedule-based control.
    B's hold causes lateness, but must not count as a disruption.
    """
    values = scenario_input(strategy, target)
    result = run_selected(tmp_path, values)
    records = [json.loads(line) for line in result.events_path.read_text().splitlines()]
    movement = ("train_id", "platform_id", "time_s")
    assert event_tuples(records, "train_arrival", movement) == [
        ("A", "P", 170),
        ("B", "P", 370),
    ]
    assert event_tuples(records, "departure_due", movement) == [
        ("A", "P", 200),
        ("B", "P", 400),
    ]
    assert event_tuples(
        records,
        "train_departure",
        (
            *movement,
            "hold_s",
            "disruption_delay_s",
            "generated_delay_s",
            "inherited_delay_s",
        ),
    ) == [("A", "P", 200, 0, 0, 0, 0), ("B", "P", departure, hold, 0, hold, 0)]
    expected_holds = [("B", 400, hold, hold, "headway_regulation")] if hold else []
    assert (
        event_tuples(
            records,
            "hold",
            ("train_id", "time_s", "requested_s", "applied_s", "reason"),
        )
        == expected_holds
    )
    expected_ends = [("B", "P", departure)] if hold else []
    assert event_tuples(records, "hold_end", movement) == expected_ends
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["control"] == values["control"]


def test_saved_headway_scenario_round_trips_exactly():
    """Saving and loading must preserve targets, search settings and weights.

    A fractional target catches rounding to whole seconds.
    Check exact values too, in case saving and loading share the same mistake.
    """
    original = load(scenario_input(target=300.25))
    saved = original.to_dict()
    restored = load(saved)
    assert restored == original
    assert saved["control"] == {
        "strategy": "headway_regulation",
        "target_headways_s": {"P": 300.25},
        "hold_search": {"step_s": 10, "max_hold_s": 90},
        "weights": {"w_wait": 1.5, "w_onboard": 0.75},
    }


def test_scenario_translates_bad_targets_to_field_error():
    """Bad targets raise the scenario loader's field-specific error.

    JSON accepts bools; target validation must reject them.
    """
    values = scenario_input(target=False)
    with pytest.raises(ScenarioValidationError, match=r"control\.target_headways_s.*P"):
        load(values)


@pytest.mark.parametrize("failure", ["return", "gap"])
def test_bad_configuration_fails_before_components_start(
    tmp_path, monkeypatch, failure
):
    """Reject bad settings before components start or write output.

    Return R starts after the 600-second cutoff but still needs a target.
    Target 75 exceeds scenario gap 60, but is below the real engine gap 90.
    """
    starts = []
    original_start = TrainComponent.start

    def record_start(component, scheduler):
        starts.append(component)
        original_start(component, scheduler)

    monkeypatch.setattr(TrainComponent, "start", record_start)
    train = Train(
        "A",
        800,
        (ScheduledStop("S", "P", 70, 100), ScheduledStop("T", "T-in", 200, 230)),
        return_trips=((ScheduledStop("T", "R", 800, 830),),),
    )
    target = 300 if failure == "return" else 75
    values = scenario_input(target=target)
    if failure == "gap":
        values["control"]["target_headways_s"]["R"] = 300
    expected = "Missing target.*R" if failure == "return" else "P.*minimum_gap_s"
    catalog = {"P", "T-in", "R"}
    trains = [train]
    with pytest.raises(ValueError, match=expected):
        run_selected(tmp_path, values, trains=trains, catalog=catalog)
    assert starts == []
    assert list(tmp_path.iterdir()) == []


def test_selected_run_accepts_gap_other_than_engine_default(tmp_path):
    """Use engine gap 45 for validation and movement, not scenario gap 120.

    Target 60 is valid against 45. The trains also arrive 60 seconds apart.
    Using gap 90 delays B's arrival to 260 and departure to 290.
    """
    values = scenario_input(target=60, scenario_gap=120)
    trains = [
        Train("A", 800, (ScheduledStop("S", "P", 170, 200),)),
        Train("B", 800, (ScheduledStop("S", "P", 230, 260),)),
    ]
    result = run_selected(tmp_path, values, engine_gap=45, trains=trains)
    records = [json.loads(line) for line in result.events_path.read_text().splitlines()]
    # Arrival gap: 230 - 170 = 60, above 45 but below 90.
    assert event_tuples(records, "train_arrival", ("train_id", "time_s")) == [
        ("A", 170),
        ("B", 230),
    ]
    # Departure gap: 260 - 200 = 60, exactly the target, so no hold.
    assert event_tuples(records, "train_departure", ("train_id", "time_s")) == [
        ("A", 200),
        ("B", 260),
    ]
    assert event_tuples(records, "hold", ("train_id", "applied_s")) == []
