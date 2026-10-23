# AI contribution: 50% or more AI-generated
"""Hand-calculated terminal recovery, Mathematical Foundations §6 (#16)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.engine.event_queue import Scheduler
from simulator.engine.events import TrainArrival, TrainDeparture
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


def vehicle(delay_s=0, slack_s=60):
    return Train(
        "vehicle",
        100,
        (ScheduledStop("A", "A-out", 0, 0), ScheduledStop("B", "B-in", 100, 100)),
        layover_slack=slack_s,
        return_trips=(
            (
                ScheduledStop("B", "B-out", 180, 180),
                ScheduledStop("A", "A-in", 280, 280),
            ),
            (
                ScheduledStop("A", "A-out", 360, 360),
                ScheduledStop("B", "B-in", 460, 460),
            ),
        ),
    )


@pytest.mark.parametrize(
    ("delay_s", "expected"), [(0, 180), (40, 180), (60, 180), (90, 210), (150, 270)]
)
def test_turnaround_absorbs_slack_once_and_keeps_vehicle(delay_s, expected):
    train = vehicle()
    train.current_stop_index = 1
    train.update_delay(100 + delay_s, 100)
    identity = id(train)
    assert train.begin_return_trip() == expected
    assert id(train) == identity
    assert train.id == "vehicle"
    assert train.capacity == 100
    # Scheduled gap is 80 s: 60 s slack leaves 20 s mandatory turnaround.
    assert expected >= 100 + delay_s + 20
    assert train.current_delay == expected - 180


def test_residual_delay_propagates_and_recovers_at_consecutive_terminals():
    train = vehicle()
    # A second train reserves the first platform and introduces 150 s lateness.
    leader = Train("leader", 100, (ScheduledStop("A", "A-out", 0, 0),))
    component = TrainComponent([leader, train], minimum_gap_s=150)
    scheduler = Scheduler()
    component.start(scheduler)
    events = []

    def process(event):
        events.append(event)
        component.handle(event, scheduler)

    scheduler.run_until(1000, process)
    arrivals = [
        e.time_s
        for e in events
        if isinstance(e, TrainArrival) and e.train_id == train.id
    ]
    assert arrivals == [150, 250, 270, 370, 390, 490]
    departures = [
        e for e in events if isinstance(e, TrainDeparture) and e.train_id == train.id
    ]
    assert [e.time_s - e.scheduled_s for e in departures] == [150, 90, 30, 30]
    assert component.trains[train.id] is train
    assert train.current_trip_index == 2


@given(delay=st.floats(min_value=0, max_value=10000, allow_nan=False))
def test_recovery_never_exceeds_slack_or_advances_before_ready(delay):
    train = vehicle()
    train.current_stop_index = 1
    train.current_delay = delay
    ready = train.begin_return_trip()
    assert train.current_delay == max(0, delay - 60)
    assert ready >= 100 + delay + 20


@pytest.mark.parametrize(
    "trip",
    [(), (ScheduledStop("C", "C", 180, 180),), (ScheduledStop("B", "B", 150, 150),)],
)
def test_invalid_return_trip_is_rejected(trip):
    with pytest.raises(ValueError):
        Train(
            "t",
            100,
            (ScheduledStop("B", "B", 100, 100),),
            layover_slack=60,
            return_trips=(trip,),
        )


def test_zero_mandatory_turnaround_respects_event_tie_order():
    train = Train(
        "t",
        10,
        (ScheduledStop("A", "A", 0, 0), ScheduledStop("B", "B-in", 100, 100)),
        current_delay=90,
        generated_delay_s=90,
        layover_slack=60,
        return_trips=((ScheduledStop("B", "B-out", 160, 160),),),
    )
    component = TrainComponent([train])
    scheduler = Scheduler()
    component.start(scheduler)
    events = []

    def process(event):
        events.append(event)
        component.handle(event, scheduler)

    scheduler.run_until(500, process)
    assert [
        (e.platform_id, e.time_s) for e in events if isinstance(e, TrainArrival)
    ] == [("A", 90), ("B-in", 190), ("B-out", 190)]
    assert train.current_delay == 30


def test_zero_slack_carries_all_delay_and_turnaround_keeps_load():
    train = vehicle(slack_s=0)
    train.current_stop_index = 1
    train.current_delay = 90
    train.board(5)
    assert train.begin_return_trip() == 270
    assert train.onboard_load == 5
    assert train.current_delay == 90


def test_return_cannot_start_before_terminal_or_consume_slack_twice():
    train = vehicle()
    with pytest.raises(ValueError, match="terminus"):
        train.begin_return_trip()
    train.current_stop_index = 1
    train.current_delay = 90
    assert train.begin_return_trip() == 210
    with pytest.raises(ValueError, match="terminus"):
        train.begin_return_trip()
    assert train.current_delay == 30
