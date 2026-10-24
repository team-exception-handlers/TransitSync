# AI contribution: 50% or more AI-generated
"""Dispatch suspension and passenger recovery, US-1.5 #27."""

import pytest

from simulator.engine.event_queue import Scheduler
from simulator.engine.events import (
    Boarding,
    PassengerArrival,
    TrainArrival,
    TrainDeparture,
)
from simulator.passengers.platform_queue import PlatformQueue
from simulator.trains.suspension import LineSuspension, dispatch_ready_s
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


def run(trains, suspensions=(), passengers=(), gap_s=10):
    queue = PlatformQueue(("P",))
    component = TrainComponent(
        trains, gap_s, suspensions=suspensions, passenger_queue=queue
    )
    scheduler = Scheduler()
    component.start(scheduler)
    for index, time_s in enumerate(passengers):
        scheduler.schedule(
            PassengerArrival(
                time_s=time_s,
                passenger_id=f"p{index}",
                group_id="burst",
                platform_id="P",
            )
        )
    events = []

    def process(event):
        events.append(event)
        component.handle(event, scheduler)

    scheduler.run_until(2000, process)
    return events, queue


def service(train_id, arrival_s, departure_s=None, line="green", capacity=2):
    return Train(
        train_id,
        capacity,
        (
            ScheduledStop(
                "A", "P", arrival_s, arrival_s if departure_s is None else departure_s
            ),
        ),
        line_id=line,
    )


@pytest.mark.parametrize(
    ("time_s", "expected"), [(99, 99), (100, 200), (199, 200), (200, 200)]
)
def test_suspension_is_half_open(time_s, expected):
    assert (
        dispatch_ready_s("green", time_s, [LineSuspension("green", 100, 200)])
        == expected
    )


def test_overlapping_and_touching_suspensions_are_combined():
    suspensions = [
        LineSuspension("green", 150, 250),
        LineSuspension("other", 0, 1000),
        LineSuspension("green", 250, 300),
        LineSuspension("green", 100, 200),
    ]
    assert dispatch_ready_s("green", 100, suspensions) == 300
    assert dispatch_ready_s("blue", 100, suspensions) == 100


def test_dispatch_resumes_in_order_with_safe_gap():
    trains = [service("one", 100), service("two", 120), service("three", 200)]
    events, _ = run(trains, [LineSuspension("green", 100, 200)])
    departures = [e for e in events if isinstance(e, TrainDeparture)]
    assert [(e.train_id, e.time_s) for e in departures] == [
        ("one", 200),
        ("two", 210),
        ("three", 220),
    ]
    assert [t.current_delay for t in trains] == [100, 90, 20]
    # The platform queue adds 80 s after the leader clears; the remaining
    # 10 s comes from the minimum departure gap, so both are inherited.
    assert trains[1].generated_delay_s == 0
    assert trains[1].inherited_delay_s == 90


def test_only_one_train_occupies_platform_during_a_suspension():
    trains = [
        service(name, arrival_s, departure_s=arrival_s + 30)
        for name, arrival_s in (("one", 0), ("two", 120), ("three", 240))
    ]
    component = TrainComponent(
        trains, 90, suspensions=[LineSuspension("green", 10, 600)]
    )
    scheduler = Scheduler()
    component.start(scheduler)
    on_platform = most_on_platform = 0

    def process(event):
        nonlocal on_platform, most_on_platform
        if isinstance(event, TrainArrival):
            on_platform += 1
        elif isinstance(event, TrainDeparture):
            on_platform -= 1
        most_on_platform = max(most_on_platform, on_platform)
        component.handle(event, scheduler)

    scheduler.run_until(2000, process)

    assert most_on_platform == 1
    assert on_platform == 0


def test_in_flight_and_other_line_services_continue():
    running = Train(
        "running",
        10,
        (ScheduledStop("A", "A", 50, 50), ScheduledStop("B", "B", 150, 150)),
        line_id="green",
    )
    other = Train("other", 10, (ScheduledStop("C", "C", 150, 150),), line_id="blue")
    events, _ = run([running, other], [LineSuspension("green", 100, 200)])
    assert [
        (e.train_id, e.time_s) for e in events if isinstance(e, TrainDeparture)
    ] == [("running", 50), ("other", 150), ("running", 150)]


def test_passengers_accumulate_then_board_fifo_up_to_capacity():
    trains = [service("one", 200), service("two", 220), service("three", 240)]
    events, queue = run(
        trains,
        [LineSuspension("green", 100, 200)],
        passengers=(110, 120, 130, 140, 150, 160, 170),
    )
    boards = [e for e in events if isinstance(e, Boarding)]
    assert [(e.passenger_id, e.train_id, e.time_s) for e in boards] == [
        ("p0", "one", 200),
        ("p1", "one", 200),
        ("p2", "two", 220),
        ("p3", "two", 220),
        ("p4", "three", 240),
        ("p5", "three", 240),
    ]
    assert queue.waiting_count("P") == 1
    assert [
        (e.boarded_count, e.onboard_load)
        for e in events
        if isinstance(e, TrainDeparture)
    ] == [(2, 2)] * 3


def test_passengers_can_board_a_train_waiting_for_dispatch():
    events, queue = run(
        [service("one", 90, 100)],
        [LineSuspension("green", 100, 200)],
        passengers=(110, 200, 201),
    )
    departure = next(e for e in events if isinstance(e, TrainDeparture))
    assert (departure.time_s, departure.boarded_count, departure.onboard_load) == (
        200,
        2,
        2,
    )
    assert queue.waiting_count("P") == 1


def test_suspension_delay_propagates_and_is_absorbed_at_terminal():
    train = Train(
        "one",
        10,
        (ScheduledStop("A", "P", 100, 100), ScheduledStop("B", "B", 200, 200)),
        line_id="green",
        layover_slack=60,
        return_trips=(
            (
                ScheduledStop("B", "B-return", 280, 280),
                ScheduledStop("A", "P", 380, 380),
            ),
        ),
    )
    events, _ = run([train], [LineSuspension("green", 100, 200)])
    arrivals = [e for e in events if isinstance(e, TrainArrival)]
    assert [e.time_s for e in arrivals] == [100, 300, 320, 420]
    assert train.current_delay == 40
    assert train.generated_delay_s == 40


def test_return_trip_dispatch_is_also_suspended():
    train = Train(
        "one",
        10,
        (
            ScheduledStop("Origin", "P", 50, 50),
            ScheduledStop("A", "terminal", 100, 100),
        ),
        line_id="green",
        layover_slack=50,
        return_trips=((ScheduledStop("A", "Q", 200, 200),),),
    )
    events, _ = run([train], [LineSuspension("green", 180, 250)])
    assert [e.time_s for e in events if isinstance(e, TrainDeparture)] == [50, 250]


@pytest.mark.parametrize(
    ("start", "end"),
    [(0, 0), (20, 10), (-1, 1), (float("nan"), 10), (0, float("inf")), (True, 10)],
)
def test_invalid_suspensions_are_rejected(start, end):
    with pytest.raises(ValueError):
        LineSuspension("green", start, end)


def test_suspension_requires_explicit_line_membership():
    with pytest.raises(ValueError, match="line IDs"):
        TrainComponent(
            [service("one", 100, line="")],
            suspensions=[LineSuspension("green", 0, 200)],
        )


def test_same_time_departures_reserve_the_gap_immediately():
    events, _ = run(
        [service("leader", 100, 210), service("follower", 190, 210)], gap_s=90
    )
    assert [e.time_s for e in events if isinstance(e, TrainDeparture)] == [210, 300]


def test_follower_cannot_overtake_leader_with_longer_dwell():
    events, _ = run([service("leader", 0, 120), service("follower", 90, 110)], gap_s=90)
    assert [
        (e.train_id, e.time_s) for e in events if isinstance(e, TrainDeparture)
    ] == [("leader", 120), ("follower", 210)]


def test_future_arrival_reservation_does_not_block_earlier_through_train():
    through = Train(
        "through",
        10,
        (ScheduledStop("A", "A", 0, 0), ScheduledStop("B", "B", 100, 100)),
    )
    future = Train("future", 10, (ScheduledStop("B", "B", 1000, 1000),))
    events, _ = run([through, future], gap_s=90)
    assert [
        (e.train_id, e.time_s)
        for e in events
        if isinstance(e, TrainArrival) and e.platform_id == "B"
    ] == [("through", 100), ("future", 1000)]
