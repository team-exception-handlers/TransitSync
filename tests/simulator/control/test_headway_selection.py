# AI contribution: 50% or more AI-generated
"""Check that saved settings control when trains leave (#48).

A leaves at 200; B is scheduled and ready at 400.
Keeping a target gap holds B; following the timetable does not.
Check what happened and which settings were saved.

Use the same arrival times and normal stop lengths in each run.
B starts on time, so its hold creates lateness.
Changing the target gap must change the hold.
"""

import json

import pytest

from simulator.scenario import ScenarioValidationError
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent
from tests.simulator.control.headway_run_helpers import (
    event_tuples,
    load,
    run_selected,
    scenario_input,
)


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

    Both targets must differ from schedule-based control.
    B's hold adds lateness, but no disruption delay.
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
    """Keep targets, search settings and weights when saving and loading.

    A fractional target catches rounding to whole seconds.
    Check exact values so matching save/load mistakes cannot pass.
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
        "prediction_error": {
            "arrival_kappa": 0.5,
            "transfer_kappa": 2.0,
            "load_kappa": 0.0,
        },
    }


def test_scenario_translates_bad_targets_to_field_error():
    """Report the target field when the loader rejects a bad value.

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
    Target 75 exceeds scenario gap 60 but is below engine gap 90.
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
