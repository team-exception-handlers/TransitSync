"""Regression tests for train separation and delay propagation."""

import json
from types import SimpleNamespace

import pytest

from simulator.engine.runner import run_scenario
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


def make_train(train_id, stops, initial_delay_s=0.0):
    return Train(
        id=train_id,
        capacity=800,
        schedule=tuple(stops),
        current_delay=initial_delay_s,
        generated_delay_s=initial_delay_s,
    )


def run_trains(tmp_path, trains):
    scenario = SimpleNamespace(
        master_seed=123,
        duration_s=2000.0,
    )

    result = run_scenario(
        scenario,
        lambda seed: None,
        lambda scenario, streams: [TrainComponent(trains, minimum_gap_s=90)],
        tmp_path,
    )

    return [json.loads(line) for line in result.events_path.read_text().splitlines()]


def movements(records, event_type, platform):
    return [
        record
        for record in records
        if record["event_type"] == event_type and record["platform_id"] == platform
    ]


def test_simultaneous_departures_respect_gap(tmp_path):
    trains = [
        make_train("A", [ScheduledStop("S", "P", 100, 210)]),
        make_train("B", [ScheduledStop("S", "P", 190, 210)]),
    ]

    records = run_trains(tmp_path, trains)
    departures = movements(records, "train_departure", "P")

    assert [r["time_s"] for r in departures] == [210, 300]


def test_follower_cannot_overtake_leader(tmp_path):
    trains = [
        make_train("A", [ScheduledStop("S", "P", 0, 120)]),
        make_train("B", [ScheduledStop("S", "P", 90, 110)]),
    ]

    records = run_trains(tmp_path, trains)
    departures = movements(records, "train_departure", "P")

    assert [r["train_id"] for r in departures] == ["A", "B"]
    assert [r["time_s"] for r in departures] == [120, 210]


def test_future_reservation_does_not_block_earlier_arrival(tmp_path):
    # Starting train deliberately appears first in the input.
    trains = [
        make_train(
            "starting",
            [ScheduledStop("B", "PB", 1000, 1020)],
        ),
        make_train(
            "through",
            [
                ScheduledStop("A", "PA", 0, 0),
                ScheduledStop("B", "PB", 100, 120),
            ],
        ),
    ]

    records = run_trains(tmp_path, trains)
    arrivals = movements(records, "train_arrival", "PB")

    assert [(r["train_id"], r["time_s"]) for r in arrivals] == [
        ("through", 100),
        ("starting", 1000),
    ]


def test_inherited_delay_is_recorded(tmp_path):
    trains = [
        make_train("A", [ScheduledStop("S", "P", 0, 120)]),
        make_train("B", [ScheduledStop("S", "P", 90, 110)]),
    ]

    records = run_trains(tmp_path, trains)
    departures = movements(records, "train_departure", "P")

    follower = departures[1]

    assert follower["time_s"] == 210
    assert follower["generated_delay_s"] == 0
    assert follower["inherited_delay_s"] == pytest.approx(100)


def test_recursive_delay_propagation(tmp_path):
    trains = [
        make_train(
            "A",
            [ScheduledStop("S", "P", 0, 20)],
            initial_delay_s=60,
        ),
        make_train("B", [ScheduledStop("S", "P", 90, 110)]),
        make_train("C", [ScheduledStop("S", "P", 180, 200)]),
    ]

    records = run_trains(tmp_path, trains)
    departures = movements(records, "train_departure", "P")

    assert [r["time_s"] for r in departures] == [80, 170, 260]

    assert [r["inherited_delay_s"] for r in departures] == [0, 60, 60]


def test_delay_not_double_counted_at_next_station(tmp_path):
    trains = [
        make_train(
            "A",
            [
                ScheduledStop("S", "P", 0, 20),
                ScheduledStop("Z", "Q", 120, 140),
            ],
            initial_delay_s=60,
        ),
        make_train(
            "B",
            [
                ScheduledStop("S", "P", 90, 110),
                ScheduledStop("Z", "Q", 210, 230),
            ],
        ),
        make_train(
            "C",
            [
                ScheduledStop("S", "P", 180, 200),
                ScheduledStop("Z", "Q", 300, 320),
            ],
        ),
    ]

    records = run_trains(tmp_path, trains)
    departures = movements(records, "train_departure", "Q")

    assert [r["time_s"] for r in departures] == [200, 290, 380]

    # Inherited delays remain 60, not 120.
    assert [r["inherited_delay_s"] for r in departures] == [0, 60, 60]


def test_full_run_respects_arrival_and_departure_gaps(tmp_path):
    trains = [
        make_train(
            "A",
            [ScheduledStop("S", "P", 0, 20)],
            initial_delay_s=60,
        ),
        make_train("B", [ScheduledStop("S", "P", 90, 110)]),
        make_train("C", [ScheduledStop("S", "P", 180, 200)]),
    ]

    records = run_trains(tmp_path, trains)

    for event_type in ("train_arrival", "train_departure"):
        events = movements(records, event_type, "P")

        assert len(events) == 3

        for previous, current in zip(events, events[1:], strict=False):
            gap = current["time_s"] - previous["time_s"]

            assert gap >= 90
