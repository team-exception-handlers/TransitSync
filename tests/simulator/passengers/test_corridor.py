# AI contribution: 50% or more AI-generated
"""Tests for the transfer corridor throughput cap (US-1.3, #20)."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.engine.event_queue import Scheduler
from simulator.engine.events import PassengerArrival
from simulator.passengers import CorridorQueue


def admit_all(queue, arrivals):
    return [
        queue.admit(f"p-{index}", arrival_s) for index, arrival_s in enumerate(arrivals)
    ]


def test_burst_is_queued_at_the_configured_throughput():
    queue = CorridorQueue(capacity_per_minute=2)

    passages = admit_all(queue, [10, 10, 10, 10])

    # At two passengers a minute, someone can pass every 30 seconds.
    assert [passage.passage_s for passage in passages] == [10, 40, 70, 100]
    assert [passage.queue_delay_s for passage in passages] == [0, 30, 60, 90]


def test_arrivals_join_an_existing_queue_in_fifo_order():
    queue = CorridorQueue(capacity_per_minute=2)

    passages = admit_all(queue, [0, 5, 50])

    # They pass at 0, 30 and 60 s, which gives waits of 0, 25 and 10 s.
    assert [passage.passage_s for passage in passages] == [0, 30, 60]
    assert [passage.queue_delay_s for passage in passages] == [0, 25, 10]


def test_arrival_at_the_next_slot_has_no_queueing_delay():
    queue = CorridorQueue(capacity_per_minute=2)

    first = queue.admit("p-1", 0)
    boundary = queue.admit("p-2", 30)

    assert first.queue_delay_s == 0
    assert boundary.passage_s == 30
    assert boundary.queue_delay_s == 0


def test_fractional_slot_boundary_has_no_rounding_delay():
    queue = CorridorQueue(capacity_per_minute=45)
    for index in range(45):
        queue.admit(f"burst-{index}", 0)

    boundary = queue.admit("boundary", 60)

    assert boundary.passage_s == 60
    assert boundary.queue_delay_s == 0


def test_idle_time_does_not_bank_future_capacity():
    queue = CorridorQueue(capacity_per_minute=2)

    passages = admit_all(queue, [0, 300, 300])

    assert [passage.passage_s for passage in passages] == [0, 300, 330]
    assert [passage.queue_delay_s for passage in passages] == [0, 0, 30]


def test_fixed_walking_times_schedule_delayed_platform_arrivals():
    train_arrival_s = 100
    walking_times_s = [20, 20, 35]
    queue = CorridorQueue(capacity_per_minute=2)
    scheduler = Scheduler()

    passages = admit_all(
        queue, [train_arrival_s + walk_s for walk_s in walking_times_s]
    )
    for passage in passages:
        scheduler.schedule(
            PassengerArrival(
                time_s=passage.passage_s,
                passenger_id=passage.passenger_id,
                group_id="rem-1",
                platform_id="metro",
            )
        )

    processed = []
    scheduler.run_until(1_000, processed.append)
    # They reach the bottleneck at 120, 120 and 135 s. With room for two
    # passengers a minute, they reach the platform at 120, 150 and 180 s.
    assert [event.time_s for event in processed] == [120, 150, 180]
    assert [passage.queue_delay_s for passage in passages] == [0, 30, 45]


def test_invalid_capacity_is_rejected():
    for capacity in (0, -1, math.nan, math.inf, True, "30"):
        with pytest.raises(ValueError, match="capacity_per_minute"):
            CorridorQueue(capacity)


def test_invalid_arrival_time_is_rejected():
    for arrival in (-1, math.nan, math.inf, True, "10"):
        with pytest.raises(ValueError, match="arrival_s"):
            CorridorQueue(30).admit("p-1", arrival)


def test_out_of_order_arrival_is_rejected_without_changing_the_queue():
    queue = CorridorQueue(capacity_per_minute=2)
    queue.admit("p-1", 20)

    with pytest.raises(ValueError, match="previous arrival"):
        queue.admit("p-2", 10)

    passage = queue.admit("p-2", 50)
    assert passage.passage_s == 50
    assert passage.queue_delay_s == 0


@given(
    capacity=st.integers(min_value=1, max_value=120),
    arrivals=st.lists(st.integers(min_value=0, max_value=3_600), max_size=50).map(
        sorted
    ),
)
def test_passage_rate_never_exceeds_capacity(capacity, arrivals):
    passages = admit_all(CorridorQueue(capacity), arrivals)
    minimum_gap_s = 60.0 / capacity

    for previous, current in zip(passages, passages[1:], strict=False):
        actual_gap_s = current.passage_s - previous.passage_s
        assert actual_gap_s > minimum_gap_s or math.isclose(
            actual_gap_s, minimum_gap_s, rel_tol=1e-12
        )
        assert current.passage_s >= current.arrival_s
        assert current.queue_delay_s >= 0
