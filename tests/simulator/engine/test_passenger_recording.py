# AI contribution: 50% or more AI-generated
"""Passenger timelines and optional logging (US-1.3, Task 1.3.6, #21)."""

import json

import pytest

from simulator.engine.event_log import PASSENGER_EVENT_TYPES
from simulator.engine.events import (
    SCHEMA_VERSION,
    Alighting,
    Boarding,
    EventType,
    MissedConnection,
    PassengerArrival,
    TrainArrival,
    event_from_record,
)
from simulator.engine.runner import run_scenario


class PassengerJourney:
    """Scripted transfers until the passenger components are available.

    Both passengers alight at 10 s. The first reaches the metro at 20 s and
    boards immediately. The second arrives at 35 s, misses a connection,
    then boards the next train at 40 s.
    """

    def __init__(self):
        self.seen = []
        self.boarded = []

    def start(self, scheduler):
        # Insert arrivals out of order to exercise the runner's event ordering.
        for passenger_id, time_s in (("p-2", 35), ("p-1", 20)):
            scheduler.schedule(
                PassengerArrival(
                    time_s=time_s,
                    passenger_id=passenger_id,
                    group_id="g-1",
                    platform_id="metro",
                )
            )
            scheduler.schedule(
                Alighting(
                    time_s=10,
                    passenger_id=passenger_id,
                    train_id="rem-1",
                    platform_id="rem",
                )
            )
        scheduler.schedule(
            TrainArrival(
                time_s=10,
                train_id="rem-1",
                station_id="mcgill",
                platform_id="rem",
                scheduled_s=10,
                disruption_delay_s=0,
            )
        )

    def handle(self, event, scheduler):
        self.seen.append(event)
        if isinstance(event, PassengerArrival):
            if event.passenger_id == "p-1":
                scheduler.schedule(
                    Boarding(
                        time_s=event.time_s,
                        passenger_id=event.passenger_id,
                        train_id="metro-1",
                        platform_id="metro",
                    )
                )
            else:
                scheduler.schedule(
                    MissedConnection(
                        time_s=event.time_s,
                        passenger_id=event.passenger_id,
                        train_id="metro-1",
                        platform_id="metro",
                    )
                )
        elif isinstance(event, MissedConnection):
            scheduler.schedule(
                Boarding(
                    time_s=40,
                    passenger_id=event.passenger_id,
                    train_id="metro-2",
                    platform_id="metro",
                )
            )
        elif isinstance(event, Boarding):
            self.boarded.append(event.passenger_id)


@pytest.fixture
def journeys():
    return []


@pytest.fixture
def build_journeys(journeys):
    def build(_scenario, _streams):
        component = PassengerJourney()
        journeys.append(component)
        return [component]

    return build


def read_records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_default_log_contains_complete_versioned_passenger_timelines(
    tmp_path,
    minimal_scenario,
    build_streams,
    build_journeys,
    journeys,
):
    result = run_scenario(minimal_scenario, build_streams, build_journeys, tmp_path)
    records = read_records(result.events_path)
    timelines = {}
    for record in records:
        if "passenger_id" in record:
            timelines.setdefault(record["passenger_id"], []).append(
                (record["event_type"], record["time_s"])
            )
    assert timelines == {
        "p-1": [("alighting", 10), ("passenger_arrival", 20), ("boarding", 20)],
        "p-2": [
            ("alighting", 10),
            ("passenger_arrival", 35),
            ("missed_connection", 35),
            ("boarding", 40),
        ],
    }
    assert all(record["schema_version"] == SCHEMA_VERSION for record in records)
    assert [event_from_record(record) for record in records] == journeys[0].seen


@pytest.mark.parametrize(
    "skipped",
    [
        frozenset(),
        PASSENGER_EVENT_TYPES,
        {EventType.BOARDING},
        {EventType.TRAIN_ARRIVAL},
        frozenset(EventType),
    ],
)
def test_log_filter_preserves_processing_and_summary(
    tmp_path,
    minimal_scenario,
    build_streams,
    build_journeys,
    journeys,
    skipped,
):
    full = run_scenario(
        minimal_scenario,
        build_streams,
        build_journeys,
        tmp_path / "full",
    )
    filtered = run_scenario(
        minimal_scenario,
        build_streams,
        build_journeys,
        tmp_path / "filtered",
        skip_event_types=skipped,
    )
    # Compare bytes as well as contents: filtering must preserve record encoding.
    expected_lines = [
        line
        for line in full.events_path.read_bytes().splitlines(keepends=True)
        if EventType(json.loads(line)["event_type"]) not in skipped
    ]
    assert filtered.events_path.read_bytes() == b"".join(expected_lines)
    assert filtered.summary_path.read_bytes() == full.summary_path.read_bytes()
    assert journeys[0].seen == journeys[1].seen
    assert journeys[0].boarded == journeys[1].boarded == ["p-1", "p-2"]
    assert filtered.summary.events_processed == 8


def test_passenger_recording_can_be_disabled_without_hiding_train_events(
    tmp_path,
    minimal_scenario,
    build_streams,
    build_journeys,
):
    result = run_scenario(
        minimal_scenario,
        build_streams,
        build_journeys,
        tmp_path,
        skip_event_types=PASSENGER_EVENT_TYPES,
    )
    records = read_records(result.events_path)
    assert [record["event_type"] for record in records] == ["train_arrival"]
    assert result.summary.events_by_type["boarding"] == 2
    assert result.summary.events_by_type["missed_connection"] == 1


def test_filtered_runs_produce_identical_output(
    tmp_path,
    minimal_scenario,
    build_streams,
    build_journeys,
):
    first = run_scenario(
        minimal_scenario,
        build_streams,
        build_journeys,
        tmp_path / "first",
        skip_event_types=PASSENGER_EVENT_TYPES,
    )
    second = run_scenario(
        minimal_scenario,
        build_streams,
        build_journeys,
        tmp_path / "second",
        skip_event_types=PASSENGER_EVENT_TYPES,
    )
    assert first.events_path.read_bytes() == second.events_path.read_bytes()
    assert first.summary_path.read_bytes() == second.summary_path.read_bytes()


@pytest.mark.parametrize(
    "invalid",
    [
        "boarding",
        {"boarding"},
        {"typo"},
        {None},
        [EventType.BOARDING],
        1,
    ],
)
def test_invalid_filter_is_rejected_before_components_or_output(
    tmp_path,
    minimal_scenario,
    build_streams,
    build_journeys,
    journeys,
    invalid,
):
    output_dir = tmp_path / "run"
    with pytest.raises(ValueError, match="skip_event_types"):
        run_scenario(
            minimal_scenario,
            build_streams,
            build_journeys,
            output_dir,
            skip_event_types=invalid,
        )
    assert journeys == []
    assert not output_dir.exists()


def test_filter_is_copied_before_components_start(
    tmp_path,
    minimal_scenario,
    build_streams,
    build_journeys,
):
    skipped = set(PASSENGER_EVENT_TYPES)

    def build(scenario, streams):
        skipped.clear()
        return build_journeys(scenario, streams)

    result = run_scenario(
        minimal_scenario,
        build_streams,
        build,
        tmp_path,
        skip_event_types=skipped,
    )
    assert [r["event_type"] for r in read_records(result.events_path)] == [
        "train_arrival",
    ]
