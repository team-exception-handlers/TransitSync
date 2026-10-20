# AI contribution: 50% or more AI-generated
"""Event types and the versioned event record schema.

Implements US-1.1 (Deterministic event engine), Task 1.1.1 (#96). Every
component of the simulator schedules and records its work as one of the
events defined here, so this module is the contract between the event queue,
the train and passenger logic, the decision engine and the metrics.

Units follow the Mathematical Foundations wiki page: every time and duration
is in seconds, and the simulation clock starts at 0.

Passenger events are recorded per passenger, matching ``PassengerEventRecord``
on the Architecture page. Only transferring passengers are modelled one by
one: each has their own walking time (pulsed arrivals, Mathematical
Foundations section 2), and per-passenger delay is a difference between two of
their event timestamps. Everyone else on the train enters the math only as
counts (onboard load L, boarding B and alighting A in sections 1 and 4), so
those counts are recorded on ``TrainDeparture`` instead of as passenger
events.

Schema versioning: any change to an event type or to the fields of an event
must increase ``SCHEMA_VERSION``. Records carry the version so that logs
written by an older engine are rejected instead of being misread.

Tie order: two events at the same time are processed in the order of
``EVENT_PRIORITY`` (lowest first), then in the order they were scheduled.
The order follows what happens at a platform in one instant:

1. ``TRAIN_ARRIVAL``: the train reaches the platform
2. ``ALIGHTING``: passengers get off before anyone gets on
3. ``PASSENGER_ARRIVAL``: a passenger reaching the platform at this instant
   can still board
4. ``BOARDING``: passengers get on during the dwell
5. ``DEPARTURE_DUE``: the dwell has ended, so the hold decision is taken now,
   once boarding at this instant is known
6. ``HOLD``: the decision taken at ``DEPARTURE_DUE`` is recorded
7. ``HOLD_END``: a hold ends, once boarding at this instant is known
8. ``TRAIN_DEPARTURE``: the train leaves
9. ``MISSED_CONNECTION``: a connection is only missed once the train has left

Every event except ``DEPARTURE_DUE`` records something that happened.
``DEPARTURE_DUE`` is the decision point of the Architecture sequence diagram:
train logic schedules it when the train arrives, and handling it builds the
observation, asks the strategy and records the ``Hold``. The decision cannot
be taken at arrival instead, because the prediction error depends on how far
ahead the strategy looks (Mathematical Foundations section 7) and Metro dwell
depends on who boards during the dwell (section 4).

Departure records: the counts on ``TrainDeparture`` are only final when the
train leaves, so the event is created at that instant and never ahead of time.
With no hold, the ``DEPARTURE_DUE`` handler creates it at the same time. With
a hold, the handler schedules a ``HOLD_END`` at the end of the hold instead,
and handling ``HOLD_END`` creates the ``TrainDeparture``. Anyone who boards
during the hold is then counted. The scheduler enforces this through
``SCHEDULE_AT_CURRENT_TIME``.
"""

import math
from dataclasses import dataclass, field, fields
from enum import StrEnum
from typing import Any, ClassVar

SCHEMA_VERSION = 3

# Field kinds, stored in dataclass field metadata and checked in __post_init__
_KIND = "kind"
_ID = "id"
_SECONDS = "seconds"
_COUNT = "count"
_TEXT = "text"


class EventType(StrEnum):
    """Every kind of event the simulation can produce."""

    TRAIN_ARRIVAL = "train_arrival"
    DEPARTURE_DUE = "departure_due"
    TRAIN_DEPARTURE = "train_departure"
    HOLD = "hold"
    HOLD_END = "hold_end"
    PASSENGER_ARRIVAL = "passenger_arrival"
    BOARDING = "boarding"
    ALIGHTING = "alighting"
    MISSED_CONNECTION = "missed_connection"
    DEPARTURE_CLEARANCE = "departure_clearance"


# Single source of truth for tie-breaking. See the module docstring for why
# the events are in this order.
EVENT_PRIORITY: dict[EventType, int] = {
    EventType.TRAIN_ARRIVAL: 0,
    EventType.ALIGHTING: 1,
    EventType.PASSENGER_ARRIVAL: 2,
    EventType.BOARDING: 3,
    EventType.DEPARTURE_DUE: 4,
    EventType.HOLD: 5,
    EventType.HOLD_END: 6,
    EventType.DEPARTURE_CLEARANCE: 7,
    EventType.TRAIN_DEPARTURE: 8,
    EventType.MISSED_CONNECTION: 9,
}

# Events whose fields are only final at the instant they happen. The scheduler
# only accepts them at the current time, so a departure can never carry counts
# taken before boarding ended (see "Departure records" above).
SCHEDULE_AT_CURRENT_TIME: frozenset[EventType] = frozenset({EventType.TRAIN_DEPARTURE})


class EventSchemaError(ValueError):
    """An event or a record does not match the event schema."""


def _id_field() -> Any:
    """Non-empty string identifier (train, station, platform or group)."""
    return field(metadata={_KIND: _ID})


def _seconds_field() -> Any:
    """Finite, non-negative time or duration in seconds."""
    return field(metadata={_KIND: _SECONDS})


def _count_field() -> Any:
    """Non-negative whole number of passengers."""
    return field(metadata={_KIND: _COUNT})


def _text_field() -> Any:
    """Non-empty free text, such as the reason for a hold decision."""
    return field(metadata={_KIND: _TEXT})


@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    """Base for all events. Instances are immutable once created.

    Attributes:
        time_s: simulation time at which the event happens, in seconds.
    """

    event_type: ClassVar[EventType]
    time_s: float = _seconds_field()

    def __post_init__(self) -> None:
        for event_field in fields(self):
            kind = event_field.metadata.get(_KIND)
            value = getattr(self, event_field.name)
            normalized = self._check_field(event_field.name, kind, value)
            # Frozen dataclass: object.__setattr__ is the documented way to
            # normalise a field during initialisation
            object.__setattr__(self, event_field.name, normalized)
        self._check_relations()

    def _check_field(self, name: str, kind: str | None, value: Any) -> Any:
        """Validate one field and return its normalised value."""
        label = f"{type(self).__name__}.{name}"
        if kind in (_ID, _TEXT):
            if not isinstance(value, str) or not value.strip():
                raise EventSchemaError(f"{label} must be a non-empty string")
            return value
        if kind == _SECONDS:
            # bool is a subclass of int, so it is excluded explicitly
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise EventSchemaError(f"{label} must be a number of seconds")
            if not math.isfinite(value) or value < 0:
                raise EventSchemaError(f"{label} must be finite and >= 0, got {value}")
            # Store as float so 10 and 10.0 serialise identically
            return float(value)
        if kind == _COUNT:
            if isinstance(value, bool) or not isinstance(value, int):
                raise EventSchemaError(f"{label} must be a whole number")
            if value < 0:
                raise EventSchemaError(f"{label} must be >= 0, got {value}")
            return value
        raise EventSchemaError(f"{label} has no field kind")

    def _check_relations(self) -> None:
        """Checks that involve more than one field. Overridden where needed."""

    def to_record(self) -> dict[str, Any]:
        """Flat record for the event log, with keys in a fixed order."""
        record: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "event_type": self.event_type.value,
        }
        for event_field in fields(self):
            record[event_field.name] = getattr(self, event_field.name)
        return record


@dataclass(frozen=True, slots=True, kw_only=True)
class TrainArrival(Event):
    """A train reaches a platform.

    Attributes:
        scheduled_s: timetabled arrival time, in seconds.
        disruption_delay_s: lateness caused by disruptions, in seconds. Delay
            caused by holds is recorded on ``Hold`` and ``TrainDeparture``,
            so the two sources stay separate.
    """

    event_type: ClassVar[EventType] = EventType.TRAIN_ARRIVAL
    train_id: str = _id_field()
    station_id: str = _id_field()
    platform_id: str = _id_field()
    scheduled_s: float = _seconds_field()
    disruption_delay_s: float = _seconds_field()


@dataclass(frozen=True, slots=True, kw_only=True)
class DepartureDue(Event):
    """A train's dwell has ended and it is ready to leave.

    This is the decision point for holding: whoever handles it decides the
    hold and records it as a ``Hold``. With no hold (or no control strategy)
    the handler creates the ``TrainDeparture`` at the same time. With a hold
    it schedules a ``HoldEnd`` at the end of the hold instead.

    Attributes:
        scheduled_s: timetabled departure time, in seconds. ``time_s`` can be
            later when the train arrived late.
    """

    event_type: ClassVar[EventType] = EventType.DEPARTURE_DUE
    train_id: str = _id_field()
    station_id: str = _id_field()
    platform_id: str = _id_field()
    scheduled_s: float = _seconds_field()


@dataclass(frozen=True, slots=True, kw_only=True)
class TrainDeparture(Event):
    """A train leaves a platform.

    The three counts cover every passenger at this stop, transferring or not,
    and use the symbols of Mathematical Foundations sections 1 and 4. The
    event is created at the moment the train leaves, while handling
    ``DepartureDue`` (no hold) or ``HoldEnd``, so the counts include anyone
    who boarded during a hold. The scheduler rejects it at any other time.

    Attributes:
        scheduled_s: timetabled departure time, in seconds.
        disruption_delay_s: lateness caused by disruptions, in seconds.
        hold_s: hold applied at this platform, in seconds. 0 if not held.
        boarded_count: passengers who boarded at this stop (B).
        alighted_count: passengers who alighted at this stop (A).
        onboard_load: passengers on board as the train leaves (L).
    """

    event_type: ClassVar[EventType] = EventType.TRAIN_DEPARTURE
    train_id: str = _id_field()
    station_id: str = _id_field()
    platform_id: str = _id_field()
    scheduled_s: float = _seconds_field()
    disruption_delay_s: float = _seconds_field()
    hold_s: float = _seconds_field()
    boarded_count: int = _count_field()
    alighted_count: int = _count_field()
    onboard_load: int = _count_field()
    generated_delay_s: float = field(default=0.0, metadata={_KIND: _SECONDS})

    inherited_delay_s: float = field(default=0.0, metadata={_KIND: _SECONDS})


@dataclass(frozen=True, slots=True, kw_only=True)
class Hold(Event):
    """A hold decision for a train at a platform.

    Records both what the strategy asked for and what the rule checking layer
    allowed (US-2.5), matching ``DecisionAuditLog`` on the Architecture page.

    Attributes:
        requested_s: hold proposed by the strategy, in seconds.
        applied_s: hold actually applied after the safety rules, in seconds.
            Never more than ``requested_s``.
        reason: why the hold was approved, reduced or refused.
    """

    event_type: ClassVar[EventType] = EventType.HOLD
    train_id: str = _id_field()
    station_id: str = _id_field()
    platform_id: str = _id_field()
    requested_s: float = _seconds_field()
    applied_s: float = _seconds_field()
    reason: str = _text_field()

    def _check_relations(self) -> None:
        # Safety rules can only shorten or refuse a hold, never extend it
        if self.applied_s > self.requested_s:
            raise EventSchemaError(
                f"Hold.applied_s ({self.applied_s}) must not exceed "
                f"Hold.requested_s ({self.requested_s})"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class HoldEnd(Event):
    """A hold on a train has ended and the train is free to leave.

    Scheduled when a hold is applied, at the decision time plus
    ``Hold.applied_s``. Whoever handles it creates the ``TrainDeparture`` at
    the same time, with the counts as they are after the hold.
    """

    event_type: ClassVar[EventType] = EventType.HOLD_END
    train_id: str = _id_field()
    station_id: str = _id_field()
    platform_id: str = _id_field()


@dataclass(frozen=True, slots=True, kw_only=True)
class PassengerArrival(Event):
    """A transferring passenger reaches the platform of their next train.

    Attributes:
        group_id: the transfer burst the passenger belongs to. All passengers
            released by one train arrival share it, so the burst size M and
            the number caught by a hold N(h) can be counted per burst
            (Mathematical Foundations sections 1 and 2).
    """

    event_type: ClassVar[EventType] = EventType.PASSENGER_ARRIVAL
    passenger_id: str = _id_field()
    group_id: str = _id_field()
    platform_id: str = _id_field()


@dataclass(frozen=True, slots=True, kw_only=True)
class Boarding(Event):
    """A transferring passenger gets on a train.

    Only recorded for passengers who fit through the doors; anyone left
    behind waits for the next train (Mathematical Foundations section 4).
    """

    event_type: ClassVar[EventType] = EventType.BOARDING
    passenger_id: str = _id_field()
    train_id: str = _id_field()
    platform_id: str = _id_field()


@dataclass(frozen=True, slots=True, kw_only=True)
class Alighting(Event):
    """A transferring passenger gets off the train that brought them."""

    event_type: ClassVar[EventType] = EventType.ALIGHTING
    passenger_id: str = _id_field()
    train_id: str = _id_field()
    platform_id: str = _id_field()


@dataclass(frozen=True, slots=True, kw_only=True)
class MissedConnection(Event):
    """A transferring passenger missed the train they were trying to catch.

    ``train_id`` is the train that left without them.
    """

    event_type: ClassVar[EventType] = EventType.MISSED_CONNECTION
    passenger_id: str = _id_field()
    train_id: str = _id_field()
    platform_id: str = _id_field()


@dataclass(frozen=True, slots=True, kw_only=True)
class DepartureClearance(Event):
    """A previously delayed train is eligible to depart"""

    event_type: ClassVar[EventType] = EventType.DEPARTURE_CLEARANCE
    train_id: str = _id_field()
    station_id: str = _id_field()
    platform_id: str = _id_field()


EVENT_CLASSES: dict[EventType, type[Event]] = {
    cls.event_type: cls
    for cls in (
        TrainArrival,
        DepartureDue,
        TrainDeparture,
        Hold,
        HoldEnd,
        PassengerArrival,
        Boarding,
        Alighting,
        MissedConnection,
        DepartureClearance,
    )
}


def event_from_record(record: dict[str, Any]) -> Event:
    """Rebuild an event from a record written by ``Event.to_record``.

    Raises:
        EventSchemaError: the schema version differs, the event type is
            unknown, or the record has missing or extra fields.
    """
    version = record.get("schema_version")
    if version != SCHEMA_VERSION:
        raise EventSchemaError(
            f"schema_version must be {SCHEMA_VERSION}, got {version!r}"
        )
    try:
        event_type = EventType(record.get("event_type"))
    except ValueError as error:
        raise EventSchemaError(
            f"event_type {record.get('event_type')!r} is not a known event type"
        ) from error

    cls = EVENT_CLASSES[event_type]
    expected = {event_field.name for event_field in fields(cls)}
    given = set(record) - {"schema_version", "event_type"}
    if missing := sorted(expected - given):
        raise EventSchemaError(f"{cls.__name__} record is missing {missing}")
    if extra := sorted(given - expected):
        raise EventSchemaError(f"{cls.__name__} record has unknown fields {extra}")
    return cls(**{name: record[name] for name in expected})
