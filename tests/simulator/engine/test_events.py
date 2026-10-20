# AI contribution: 50% or more AI-generated
"""Tests for the event types and record schema (US-1.1, Task 1.1.1, #96)."""

import dataclasses
import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.engine.events import (
    EVENT_CLASSES,
    EVENT_PRIORITY,
    SCHEMA_VERSION,
    Alighting,
    Boarding,
    DepartureDue,
    EventSchemaError,
    EventType,
    Hold,
    HoldEnd,
    MissedConnection,
    PassengerArrival,
    TrainArrival,
    TrainDeparture,
    event_from_record,
)

# One valid instance of every event type, reused by the round-trip tests
SAMPLE_EVENTS = [
    TrainArrival(
        time_s=120.0,
        train_id="rem-1",
        station_id="mcgill",
        platform_id="STA_ZCD_BT_QUAI_01_MCG",
        scheduled_s=100.0,
        disruption_delay_s=20.0,
    ),
    TrainDeparture(
        time_s=180.0,
        train_id="metro-1",
        station_id="mcgill",
        platform_id="green-west",
        scheduled_s=150.0,
        disruption_delay_s=0.0,
        hold_s=30.0,
        boarded_count=85,
        alighted_count=60,
        onboard_load=640,
    ),
    Hold(
        time_s=150.0,
        train_id="metro-1",
        station_id="mcgill",
        platform_id="green-west",
        requested_s=45.0,
        applied_s=30.0,
        reason="reduced to maximum hold",
    ),
    PassengerArrival(
        time_s=140.0, passenger_id="p-1", group_id="g-1", platform_id="green-west"
    ),
    Boarding(
        time_s=145.0, passenger_id="p-1", train_id="metro-1", platform_id="green-west"
    ),
    Alighting(
        time_s=125.0,
        passenger_id="p-1",
        train_id="rem-1",
        platform_id="STA_ZCD_BT_QUAI_01_MCG",
    ),
    MissedConnection(
        time_s=180.0, passenger_id="p-2", train_id="metro-1", platform_id="green-west"
    ),
    HoldEnd(
        time_s=180.0, train_id="metro-1", station_id="mcgill", platform_id="green-west"
    ),
    DepartureDue(
        time_s=150.0,
        train_id="metro-1",
        station_id="mcgill",
        platform_id="green-west",
        scheduled_s=150.0,
    ),
]


def _arrival(time_s=10.0, passenger_id="p-1"):
    """Valid PassengerArrival with one field overridable, for edge tests."""
    return PassengerArrival(
        time_s=time_s, passenger_id=passenger_id, group_id="g-1", platform_id="p"
    )


def _departure(**overrides):
    """Valid TrainDeparture with any field overridable, for edge tests."""
    values = {
        "time_s": 60.0,
        "train_id": "t",
        "station_id": "s",
        "platform_id": "p",
        "scheduled_s": 60.0,
        "disruption_delay_s": 0.0,
        "hold_s": 0.0,
        "boarded_count": 0,
        "alighted_count": 0,
        "onboard_load": 0,
    }
    return TrainDeparture(**(values | overrides))


def test_event_types_match_the_issue_list_plus_the_decision_points():
    # The seven types listed in Task 1.1.1, plus departure_due, where the hold
    # decision is taken (Architecture sequence diagram), and hold_end, where a
    # held train's departure record is created
    assert {event_type.value for event_type in EventType} == {
        "train_arrival",
        "departure_due",
        "departure_clearance",
        "train_departure",
        "hold",
        "hold_end",
        "passenger_arrival",
        "boarding",
        "alighting",
        "missed_connection",
    }


def test_every_event_type_has_a_class_and_a_unique_priority():
    assert set(EVENT_CLASSES) == set(EventType)
    assert set(EVENT_PRIORITY) == set(EventType)
    assert len(set(EVENT_PRIORITY.values())) == len(EventType)


def test_priority_order_matches_the_documented_platform_sequence():
    ordered = sorted(EventType, key=EVENT_PRIORITY.__getitem__)
    assert ordered == [
        EventType.TRAIN_ARRIVAL,
        EventType.ALIGHTING,
        EventType.PASSENGER_ARRIVAL,
        EventType.BOARDING,
        EventType.DEPARTURE_DUE,
        EventType.HOLD,
        EventType.HOLD_END,
        EventType.DEPARTURE_CLEARANCE,
        EventType.TRAIN_DEPARTURE,
        EventType.MISSED_CONNECTION,
    ]


def test_departure_due_record_has_fixed_keys_and_values():
    assert list(SAMPLE_EVENTS[-1].to_record().items()) == [
        ("schema_version", SCHEMA_VERSION),
        ("event_type", "departure_due"),
        ("time_s", 150.0),
        ("train_id", "metro-1"),
        ("station_id", "mcgill"),
        ("platform_id", "green-west"),
        ("scheduled_s", 150.0),
    ]


def test_departure_due_after_a_late_arrival_keeps_the_timetabled_time():
    # Train arrived 20 s late, so its dwell ends 20 s after the timetable
    due = DepartureDue(
        time_s=170.0,
        train_id="t",
        station_id="s",
        platform_id="p",
        scheduled_s=150.0,
    )
    assert (due.time_s, due.scheduled_s) == (170.0, 150.0)


def test_departure_record_has_fixed_keys_and_values():
    record = SAMPLE_EVENTS[1].to_record()
    assert list(record.items()) == [
        ("schema_version", SCHEMA_VERSION),
        ("event_type", "train_departure"),
        ("time_s", 180.0),
        ("train_id", "metro-1"),
        ("station_id", "mcgill"),
        ("platform_id", "green-west"),
        ("scheduled_s", 150.0),
        ("disruption_delay_s", 0.0),
        ("hold_s", 30.0),
        ("boarded_count", 85),
        ("alighted_count", 60),
        ("onboard_load", 640),
        ("generated_delay_s", 0.0),
        ("inherited_delay_s", 0.0),
    ]


def test_passenger_events_identify_one_passenger_without_a_count():
    passenger_classes = [PassengerArrival, Boarding, Alighting, MissedConnection]
    for cls in passenger_classes:
        names = {event_field.name for event_field in dataclasses.fields(cls)}
        assert "passenger_id" in names
        assert "count" not in names


@pytest.mark.parametrize("event", SAMPLE_EVENTS, ids=lambda e: e.event_type.value)
def test_record_round_trip_gives_an_equal_event(event):
    assert event_from_record(event.to_record()) == event


def test_integer_seconds_are_stored_as_float():
    # 10 and 10.0 must serialise the same way for byte-identical logs
    event = _arrival(time_s=10)
    assert event.time_s == 10.0
    assert isinstance(event.time_s, float)


def test_events_are_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        SAMPLE_EVENTS[0].time_s = 0.0


@pytest.mark.parametrize("bad_time", [-0.5, math.nan, math.inf, "10", True])
def test_invalid_time_is_rejected_naming_the_field(bad_time):
    with pytest.raises(EventSchemaError, match=r"PassengerArrival\.time_s"):
        _arrival(time_s=bad_time)


def test_zero_time_is_accepted_as_the_clock_start():
    assert _arrival(time_s=0).time_s == 0.0


@pytest.mark.parametrize("bad_id", ["", "   ", None, 7])
def test_invalid_identifier_is_rejected_naming_the_field(bad_id):
    with pytest.raises(EventSchemaError, match=r"PassengerArrival\.passenger_id"):
        _arrival(passenger_id=bad_id)


@pytest.mark.parametrize("bad_count", [-1, 2.5, True])
def test_invalid_count_is_rejected_naming_the_field(bad_count):
    with pytest.raises(EventSchemaError, match=r"TrainDeparture\.onboard_load"):
        _departure(onboard_load=bad_count)


def test_empty_train_departure_counts_are_accepted():
    # A train can leave a stop where nobody boards or alights
    departure = _departure()
    assert (departure.boarded_count, departure.alighted_count) == (0, 0)


def test_hold_applied_longer_than_requested_is_rejected():
    with pytest.raises(EventSchemaError, match="must not exceed"):
        Hold(
            time_s=10.0,
            train_id="t",
            station_id="s",
            platform_id="p",
            requested_s=30.0,
            applied_s=30.5,
            reason="approved",
        )


def test_hold_applied_equal_to_requested_is_accepted():
    hold = Hold(
        time_s=10.0,
        train_id="t",
        station_id="s",
        platform_id="p",
        requested_s=30.0,
        applied_s=30.0,
        reason="approved",
    )
    assert hold.applied_s == hold.requested_s == 30.0


def test_hold_without_reason_is_rejected():
    with pytest.raises(EventSchemaError, match=r"Hold\.reason"):
        Hold(
            time_s=10.0,
            train_id="t",
            station_id="s",
            platform_id="p",
            requested_s=0.0,
            applied_s=0.0,
            reason="",
        )


def test_record_from_another_schema_version_is_rejected():
    record = SAMPLE_EVENTS[0].to_record() | {"schema_version": SCHEMA_VERSION + 1}
    with pytest.raises(EventSchemaError, match="schema_version"):
        event_from_record(record)


def test_record_with_unknown_event_type_is_rejected():
    record = SAMPLE_EVENTS[0].to_record() | {"event_type": "teleport"}
    with pytest.raises(EventSchemaError, match="teleport"):
        event_from_record(record)


def test_record_with_missing_field_is_rejected_naming_it():
    record = SAMPLE_EVENTS[0].to_record()
    del record["platform_id"]
    with pytest.raises(EventSchemaError, match="platform_id"):
        event_from_record(record)


def test_record_with_extra_field_is_rejected_naming_it():
    record = SAMPLE_EVENTS[0].to_record() | {"speed": 3}
    with pytest.raises(EventSchemaError, match="speed"):
        event_from_record(record)


@given(
    time_s=st.floats(min_value=0, max_value=1e6, allow_nan=False),
    load=st.integers(min_value=0, max_value=10_000),
    passenger_id=st.text(min_size=1).filter(str.strip),
)
def test_any_valid_event_survives_a_round_trip(time_s, load, passenger_id):
    arrival = _arrival(time_s=time_s, passenger_id=passenger_id)
    departure = _departure(time_s=time_s, onboard_load=load)
    assert event_from_record(arrival.to_record()) == arrival
    assert event_from_record(departure.to_record()) == departure
