# AI contribution: 50% or more AI-generated
"""Test selected timetable control through the runner and train engine (#47).

Both policies use the same timetable: 100/130 at P1, then 200/230 at P2.
In both runs, the train arrives at 90 seconds and finishes its dwell at 120.
The selected policy determines whether it leaves then or waits until 130.
"""

import json
from datetime import date

import pytest

from simulator.control.decision import DecisionPipeline
from simulator.control.strategies import STRATEGIES
from simulator.engine.events import PassengerArrival
from simulator.engine.random_streams import StreamManager
from simulator.engine.runner import run_scenario
from simulator.passengers.platform_queue import PlatformQueue
from simulator.scenario import DatasetMetadata, load_scenario_json
from simulator.trains.suspension import LineSuspension
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent

TIMETABLE = (
    ScheduledStop("S1", "P1", 100, 130),
    ScheduledStop("S2", "P2", 200, 230),
)


class PassengerDuringHold:
    """Send one passenger to the platform during the 120–130 second hold."""

    def start(self, scheduler):
        """Schedule arrival at 125 seconds; TrainComponent handles boarding."""
        scheduler.schedule(
            PassengerArrival(
                time_s=125,
                passenger_id="p1",
                group_id="burst",
                platform_id="P1",
            )
        )

    def handle(self, event, scheduler):
        """No event handling is needed after scheduling the arrival."""


def selected_scenario(strategy):
    """Validate the selected policy using local test dataset metadata."""
    dataset = DatasetMetadata(
        dataset_id="test",
        coverage_start=date(2026, 10, 5),
        coverage_end=date(2026, 10, 5),
        service_day_end_s_by_interchange={"mcgill": 86400},
        interchange_ids=frozenset({"mcgill"}),
    )
    return load_scenario_json(
        json.dumps(
            {
                "dataset_id": "test",
                "date": "2026-10-05",
                "start_time": "07:00",
                "duration_s": 600,
                "master_seed": 7,
                "interchanges": ["mcgill"],
                "control": {"strategy": strategy},
            }
        ),
        {dataset.dataset_id: dataset},
    )


def run_selected(output_dir, strategy="schedule_based", delay_s=-10, *, blocked=False):
    """Run fresh trains and components; return the result and event records.

    ``delay_s`` is the initial schedule offset in seconds, negative when early.
    ``blocked`` suspends dispatch until 150, after the timetable hold ends.
    """
    scenario = selected_scenario(strategy)
    train = Train(
        id="A",
        capacity=800,
        schedule=TIMETABLE,
        current_delay=delay_s,
        generated_delay_s=max(0, delay_s),
        line_id="green",
    )

    def build_components(settings, _streams):
        # Keep policy assembly in the component factory.
        policy = STRATEGIES.build(settings.control.strategy)
        return [
            TrainComponent(
                [train],
                decision=DecisionPipeline(policy),
                passenger_queue=PlatformQueue(("P1", "P2")),
                suspensions=[LineSuspension("green", 125, 150)] if blocked else (),
            ),
            PassengerDuringHold(),
        ]

    result = run_scenario(scenario, StreamManager, build_components, output_dir)
    records = [json.loads(line) for line in result.events_path.read_text().splitlines()]
    assert train.schedule == TIMETABLE
    return result, records


def events(records, event_type):
    """Return all records of the requested event type."""
    return [record for record in records if record["event_type"] == event_type]


def movements(records, event_type):
    """Return train ID, platform ID and actual time in seconds for each event."""
    return [
        (record["train_id"], record["platform_id"], record["time_s"])
        for record in events(records, event_type)
    ]


def test_selected_schedule_policy_holds_early_train_in_full_run(tmp_path):
    """Check when the train arrives and leaves under each policy.

    The train arrives at 90 seconds and is ready to leave after a 30-second dwell.
    Schedule control holds it until 130, so it reaches the next stop at 200.
    Comparing every event also catches missing or duplicate movements.
    """
    _, uncontrolled = run_selected(tmp_path / "no-control", "no_control")
    _, controlled = run_selected(tmp_path / "schedule")
    assert events(uncontrolled, "hold") == []
    assert events(uncontrolled, "hold_end") == []
    assert movements(uncontrolled, "train_arrival") == [
        ("A", "P1", 90),
        ("A", "P2", 190),
    ]
    assert movements(uncontrolled, "train_departure") == [
        ("A", "P1", 120),
        ("A", "P2", 220),
    ]
    assert [record["hold_s"] for record in events(uncontrolled, "train_departure")] == [
        0,
        0,
    ]
    assert movements(controlled, "hold") == [("A", "P1", 120)]
    hold = events(controlled, "hold")[0]
    assert (hold["requested_s"], hold["applied_s"], hold["reason"]) == (
        10,
        10,
        "schedule_based",
    )
    assert movements(controlled, "hold_end") == [("A", "P1", 130)]
    assert movements(controlled, "train_arrival") == [("A", "P1", 90), ("A", "P2", 200)]
    assert movements(controlled, "train_departure") == [
        ("A", "P1", 130),
        ("A", "P2", 230),
    ]
    assert [record["hold_s"] for record in events(controlled, "train_departure")] == [
        10,
        0,
    ]


@pytest.mark.parametrize("delay_s", [0, 10], ids=["on-time", "late"])
def test_on_time_and_late_schedule_runs_have_no_hold_events(tmp_path, delay_s):
    """On-time and late trains finish both stops without a timetable hold."""
    _, records = run_selected(tmp_path, delay_s=delay_s)
    assert events(records, "hold") == []
    assert events(records, "hold_end") == []
    assert movements(records, "train_arrival") == [
        ("A", "P1", 100 + delay_s),
        ("A", "P2", 200 + delay_s),
    ]
    assert movements(records, "train_departure") == [
        ("A", "P1", 130 + delay_s),
        ("A", "P2", 230 + delay_s),
    ]
    assert [record["hold_s"] for record in events(records, "train_departure")] == [0, 0]


def test_schedule_hold_allows_boarding_until_departure(tmp_path):
    """A passenger arriving at 125 boards before departure at 130.

    Count the passenger once and keep them onboard at the next stop.
    """
    _, records = run_selected(tmp_path)
    assert movements(records, "boarding") == [("A", "P1", 125)]
    assert [record["passenger_id"] for record in events(records, "boarding")] == ["p1"]
    first, second = events(records, "train_departure")
    assert (first["time_s"], first["boarded_count"], first["onboard_load"]) == (
        130,
        1,
        1,
    )
    assert (second["boarded_count"], second["onboard_load"]) == (0, 1)


def test_schedule_hold_end_precedes_departure_when_dispatch_is_blocked(tmp_path):
    """The train must wait for dispatch permission even after its hold ends.

    The hold ends at 130 seconds, but the train cannot leave until 150.
    It reaches the next stop 20 seconds late and needs no further hold.
    """
    _, records = run_selected(tmp_path, blocked=True)
    # The hold ends at 130, but dispatch stays blocked until 150.
    assert movements(records, "hold") == [("A", "P1", 120)]
    assert movements(records, "hold_end") == [("A", "P1", 130)]
    assert movements(records, "train_departure") == [("A", "P1", 150), ("A", "P2", 250)]
    assert [record["hold_s"] for record in events(records, "train_departure")] == [
        10,
        0,
    ]


def test_manifest_records_executed_schedule_strategy(tmp_path):
    """Check that the recorded policy also controls actual departures."""
    result, records = run_selected(tmp_path)
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["control"] == {"strategy": "schedule_based"}
    assert movements(records, "hold") == [("A", "P1", 120)]
    assert movements(records, "train_departure") == [("A", "P1", 130), ("A", "P2", 230)]


def test_schedule_runs_are_byte_reproducible(tmp_path):
    """Running the same scenario twice produces identical results.

    Check that the train actually moves and holds, so empty logs cannot pass.
    """
    first, first_records = run_selected(tmp_path / "first")
    second, second_records = run_selected(tmp_path / "second")
    assert movements(first_records, "hold") == [("A", "P1", 120)]
    assert movements(second_records, "train_departure") == [
        ("A", "P1", 130),
        ("A", "P2", 230),
    ]
    assert first.events_path.read_bytes() == second.events_path.read_bytes()
    assert first.summary_path.read_bytes() == second.summary_path.read_bytes()
    first_manifest = json.loads(first.manifest_path.read_text())
    second_manifest = json.loads(second.manifest_path.read_text())
    # The recording timestamp changes between runs.
    first_manifest.pop("timestamp")
    second_manifest.pop("timestamp")
    assert first_manifest == second_manifest
