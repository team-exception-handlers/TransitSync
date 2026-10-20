# AI contribution: 50% or more AI-generated
"""Tests for the event queue and simulation clock (US-1.1, Task 1.1.2, #8)."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.engine.event_queue import (
    EmptyQueueError,
    EventQueue,
    Scheduler,
    SchedulingError,
)
from simulator.engine.events import (
    EVENT_PRIORITY,
    SCHEDULE_AT_CURRENT_TIME,
    Alighting,
    Boarding,
    CorridorArrival,
    DepartureClearance,
    DepartureDue,
    EventType,
    Hold,
    HoldEnd,
    MissedConnection,
    PassengerArrival,
    TrainArrival,
    TrainDeparture,
)


def make_event(event_type, time_s, tag="x"):
    """Valid event of the given type and time. ``tag`` tells events apart."""
    train = {"train_id": f"t-{tag}", "station_id": "s", "platform_id": "p"}
    passenger = {"passenger_id": f"p-{tag}", "platform_id": "p"}
    builders = {
        EventType.TRAIN_ARRIVAL: lambda: TrainArrival(
            time_s=time_s, scheduled_s=time_s, disruption_delay_s=0, **train
        ),
        EventType.DEPARTURE_DUE: lambda: DepartureDue(
            time_s=time_s, scheduled_s=time_s, **train
        ),
        EventType.TRAIN_DEPARTURE: lambda: TrainDeparture(
            time_s=time_s,
            scheduled_s=time_s,
            disruption_delay_s=0,
            hold_s=0,
            boarded_count=0,
            alighted_count=0,
            onboard_load=0,
            **train,
        ),
        EventType.HOLD: lambda: Hold(
            time_s=time_s, requested_s=0, applied_s=0, reason="none", **train
        ),
        EventType.HOLD_END: lambda: HoldEnd(time_s=time_s, **train),
        EventType.PASSENGER_ARRIVAL: lambda: PassengerArrival(
            time_s=time_s, group_id="g", **passenger
        ),
        EventType.CORRIDOR_ARRIVAL: lambda: CorridorArrival(
            time_s=time_s, group_id="g", **passenger
        ),
        EventType.BOARDING: lambda: Boarding(time_s=time_s, train_id="t", **passenger),
        EventType.ALIGHTING: lambda: Alighting(
            time_s=time_s, train_id="t", **passenger
        ),
        EventType.MISSED_CONNECTION: lambda: MissedConnection(
            time_s=time_s, train_id="t", **passenger
        ),
        EventType.DEPARTURE_CLEARANCE: lambda: DepartureClearance(
            time_s=time_s,
            **train,
        ),
    }
    return builders[event_type]()


def run_all(scheduler, end_s=1e9):
    """Process every event up to ``end_s`` and return them in order."""
    processed = []
    scheduler.run_until(end_s, processed.append)
    return processed


def test_events_scheduled_out_of_order_are_processed_in_time_order():
    scheduler = Scheduler()
    for time_s in (30.0, 10.0, 20.0):
        scheduler.schedule(make_event(EventType.PASSENGER_ARRIVAL, time_s))
    assert [event.time_s for event in run_all(scheduler)] == [10.0, 20.0, 30.0]


def test_same_time_events_resolve_by_documented_priority():
    # Scheduled in reverse platform order; processed arrival -> boarding ->
    # departure due, as documented in simulator.engine.events
    scheduler = Scheduler()
    for event_type in (
        EventType.DEPARTURE_DUE,
        EventType.BOARDING,
        EventType.TRAIN_ARRIVAL,
    ):
        scheduler.schedule(make_event(event_type, 50.0))
    assert [event.event_type for event in run_all(scheduler)] == [
        EventType.TRAIN_ARRIVAL,
        EventType.BOARDING,
        EventType.DEPARTURE_DUE,
    ]


@pytest.mark.parametrize("tags", [("a", "b", "c"), ("c", "a", "b")])
def test_same_time_same_type_events_keep_scheduling_order(tags):
    scheduler = Scheduler()
    for tag in tags:
        scheduler.schedule(make_event(EventType.PASSENGER_ARRIVAL, 5.0, tag))
    processed = run_all(scheduler)
    assert [event.passenger_id for event in processed] == [f"p-{t}" for t in tags]


def test_clock_starts_at_zero():
    assert Scheduler().now == 0.0


def test_clock_jumps_to_each_event_time_without_fixed_steps():
    scheduler = Scheduler()
    for time_s in (10.0, 250.0):
        scheduler.schedule(make_event(EventType.PASSENGER_ARRIVAL, time_s))
    clock_seen = []
    scheduler.run_until(1000.0, lambda _event: clock_seen.append(scheduler.now))
    # 0 -> 10 -> 250: no intermediate values, and the clock does not move on
    # to the end of the period after the last event
    assert clock_seen == [10.0, 250.0]
    assert scheduler.now == 250.0


def test_handler_can_schedule_follow_up_events():
    scheduler = Scheduler()
    scheduler.schedule(make_event(EventType.TRAIN_ARRIVAL, 100.0))

    def handler(event):
        if event.event_type is EventType.TRAIN_ARRIVAL:
            # Same instant but later in the tie order, then a later time
            scheduler.schedule(make_event(EventType.ALIGHTING, 100.0))
            scheduler.schedule(make_event(EventType.DEPARTURE_DUE, 130.0))

    processed = []
    scheduler.run_until(1000.0, lambda e: (processed.append(e), handler(e)))
    assert [(e.event_type, e.time_s) for e in processed] == [
        (EventType.TRAIN_ARRIVAL, 100.0),
        (EventType.ALIGHTING, 100.0),
        (EventType.DEPARTURE_DUE, 130.0),
    ]


def test_hold_decision_at_departure_due_can_record_and_delay_the_departure():
    # Sequence diagram flow: dwell ends at 150 s, a 30 s hold is decided and
    # recorded at 150 s, the hold ends at 180 s and the departure is created
    # then, at the moment the train leaves
    scheduler = Scheduler()
    scheduler.schedule(make_event(EventType.DEPARTURE_DUE, 150.0))

    def handler(event):
        if event.event_type is EventType.DEPARTURE_DUE:
            scheduler.schedule(make_event(EventType.HOLD, 150.0))
            scheduler.schedule(make_event(EventType.HOLD_END, 180.0))
        elif event.event_type is EventType.HOLD_END:
            scheduler.schedule(make_event(EventType.TRAIN_DEPARTURE, 180.0))

    processed = []
    scheduler.run_until(1000.0, lambda e: (processed.append(e), handler(e)))
    assert [(e.event_type, e.time_s) for e in processed] == [
        (EventType.DEPARTURE_DUE, 150.0),
        (EventType.HOLD, 150.0),
        (EventType.HOLD_END, 180.0),
        (EventType.TRAIN_DEPARTURE, 180.0),
    ]


def test_departure_scheduled_ahead_of_time_is_rejected():
    # Created at the 150 s decision for a 180 s departure, its counts would
    # miss anyone boarding during the hold
    scheduler = Scheduler()
    scheduler.schedule(make_event(EventType.DEPARTURE_DUE, 150.0))
    run_all(scheduler)
    with pytest.raises(SchedulingError, match="must be created when it happens"):
        scheduler.schedule(make_event(EventType.TRAIN_DEPARTURE, 180.0))
    assert scheduler.pending == 0


def test_departure_at_the_current_time_is_accepted():
    scheduler = Scheduler()
    scheduler.schedule(make_event(EventType.DEPARTURE_DUE, 150.0))
    run_all(scheduler)
    scheduler.schedule(make_event(EventType.TRAIN_DEPARTURE, 150.0))
    processed = run_all(scheduler)
    assert [e.event_type for e in processed] == [EventType.TRAIN_DEPARTURE]


def test_scheduling_before_the_clock_is_rejected():
    scheduler = Scheduler()
    scheduler.schedule(make_event(EventType.PASSENGER_ARRIVAL, 100.0))
    run_all(scheduler)
    with pytest.raises(SchedulingError, match="clock is already at 100.0"):
        scheduler.schedule(make_event(EventType.PASSENGER_ARRIVAL, 50.0))


def test_scheduling_earlier_in_tie_order_at_current_time_is_rejected():
    # Boarding at 100 s cannot happen after the hold ended at 100 s
    scheduler = Scheduler()
    scheduler.schedule(make_event(EventType.HOLD_END, 100.0))
    run_all(scheduler)
    with pytest.raises(SchedulingError, match="tie order"):
        scheduler.schedule(make_event(EventType.BOARDING, 100.0))


def test_scheduling_same_type_at_current_time_is_allowed():
    scheduler = Scheduler()
    scheduler.schedule(make_event(EventType.PASSENGER_ARRIVAL, 100.0, "a"))
    run_all(scheduler)
    scheduler.schedule(make_event(EventType.PASSENGER_ARRIVAL, 100.0, "b"))
    assert [event.passenger_id for event in run_all(scheduler)] == ["p-b"]


def test_step_on_empty_queue_raises_a_clear_error():
    with pytest.raises(EmptyQueueError, match="empty"):
        Scheduler().step()


def test_pop_on_empty_queue_raises_and_peek_returns_none():
    queue = EventQueue()
    assert queue.peek_time() is None
    with pytest.raises(EmptyQueueError):
        queue.pop()


def test_event_exactly_at_end_is_processed_and_later_events_wait():
    scheduler = Scheduler()
    for time_s in (60.0, 60.5):
        scheduler.schedule(make_event(EventType.PASSENGER_ARRIVAL, time_s))
    assert scheduler.run_until(60.0, lambda _event: None) == 1
    assert scheduler.pending == 1
    assert scheduler.now == 60.0


def test_run_until_with_empty_queue_processes_nothing():
    scheduler = Scheduler()
    assert scheduler.run_until(3600.0, lambda _event: None) == 0
    assert scheduler.now == 0.0


@pytest.mark.parametrize("bad_end", [-1.0, math.nan, math.inf])
def test_invalid_end_time_is_rejected(bad_end):
    with pytest.raises(SchedulingError, match="end_s"):
        Scheduler().run_until(bad_end, lambda _event: None)


def test_end_time_before_the_clock_is_rejected():
    scheduler = Scheduler()
    scheduler.schedule(make_event(EventType.PASSENGER_ARRIVAL, 100.0))
    run_all(scheduler)
    with pytest.raises(SchedulingError, match="end_s"):
        scheduler.run_until(50.0, lambda _event: None)


# Types that may be scheduled ahead of time. The others can only be scheduled
# at the current time, which the dedicated tests above cover.
_AHEAD_TYPES = [t for t in EventType if t not in SCHEDULE_AT_CURRENT_TIME]

# Small times keep collisions (ties) frequent in generated cases
_scheduled = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=20).map(float),
        st.sampled_from(_AHEAD_TYPES),
    ),
    max_size=40,
)


def _order_keys(events):
    return [(e.time_s, EVENT_PRIORITY[e.event_type]) for e in events]


@given(_scheduled)
def test_processing_order_never_goes_backwards(scheduled):
    scheduler = Scheduler()
    for index, (time_s, event_type) in enumerate(scheduled):
        scheduler.schedule(make_event(event_type, time_s, str(index)))
    clock_seen = []
    processed = []

    def handler(event):
        clock_seen.append(scheduler.now)
        processed.append(event)

    scheduler.run_until(1e9, handler)
    assert len(processed) == len(scheduled)
    assert _order_keys(processed) == sorted(_order_keys(processed))
    assert clock_seen == sorted(clock_seen)


@given(st.permutations(_AHEAD_TYPES), st.randoms(use_true_random=False))
def test_order_does_not_depend_on_scheduling_order_for_distinct_keys(event_types, rng):
    # Distinct (time, priority) keys: scheduling order must not matter
    events = [make_event(t, float(i % 3)) for i, t in enumerate(event_types)]
    shuffled = list(events)
    rng.shuffle(shuffled)

    first, second = Scheduler(), Scheduler()
    for event in events:
        first.schedule(event)
    for event in shuffled:
        second.schedule(event)
    assert run_all(first) == run_all(second)
