# AI contribution: Below 50% AI-generated
"""Tests for the controller interface (US-2.1, Task 2.1.1, #37)."""

import dataclasses
import math
from collections import deque

import pytest

from simulator.control.interface import (
    DecisionController,
    HoldAction,
    IncomingTransfer,
    ObservationSnapshot,
    PlatformState,
    TrainState,
)

TRAIN = TrainState(
    train_id="rem_0001",
    line_id="rem",
    next_platform_id="rem_mcgill_0",
    predicted_arrival_s=240.0,
    scheduled_departure_s=270.0,
    delay_s=15.0,
    onboard_load=320,
    capacity=780,
)
PLATFORM = PlatformState(
    platform_id="rem_mcgill_0", waiting_count=42, last_departure_s=60.0
)
TRANSFER = IncomingTransfer(
    group_id="xfer-group-000001",
    platform_id="rem_mcgill_0",
    passenger_count=18,
    first_arrival_s=150.0,
    last_arrival_s=210.0,
    feeder_arrival_s=90.0,
    group_size=40,
)


def make_snapshot(**overrides) -> ObservationSnapshot:
    """A valid snapshot at McGill, with any field replaced by ``overrides``."""
    values = {
        "time_s": 120.0,
        "train_id": "rem_0001",
        "station_id": "mcgill",
        "platform_id": "rem_mcgill_0",
        "trains": (TRAIN,),
        "platforms": (PLATFORM,),
        "incoming_transfers": (TRANSFER,),
    }
    values.update(overrides)
    return ObservationSnapshot(**values)


class MutatingStrategy(DecisionController):
    """Breaks the read-only rule on purpose, to show it cannot succeed."""

    name = "mutating"

    def evaluate(self, observation: ObservationSnapshot) -> tuple[HoldAction, ...]:
        observation.time_s = 0.0
        return ()


class FixedHoldStrategy(DecisionController):
    """Always asks for a 30 s hold on the deciding train."""

    name = "fixed_hold"

    def evaluate(self, observation: ObservationSnapshot) -> tuple[HoldAction, ...]:
        return (HoldAction(observation.train_id, 30.0, "test hold"),)


def test_strategy_cannot_mutate_observation():
    snapshot = make_snapshot()
    strategy = MutatingStrategy()
    with pytest.raises(dataclasses.FrozenInstanceError):
        strategy.evaluate(snapshot)
    assert snapshot.time_s == 120.0


@pytest.mark.parametrize("value", [TRAIN, PLATFORM, TRANSFER])
def test_snapshot_parts_are_frozen(value):
    first_field = dataclasses.fields(value)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(value, first_field, "changed")


def test_snapshot_collections_cannot_grow():
    snapshot = make_snapshot()
    # Tuples have no append, so a strategy cannot add trains to the snapshot
    assert not hasattr(snapshot.trains, "append")
    assert snapshot.trains == (TRAIN,)


@pytest.mark.parametrize("field_name", ["trains", "platforms", "incoming_transfers"])
@pytest.mark.parametrize("mutable_type", [list, deque])
def test_snapshot_rejects_mutable_collections(field_name, mutable_type):
    original = getattr(make_snapshot(), field_name)
    with pytest.raises(ValueError, match=field_name):
        make_snapshot(**{field_name: mutable_type(original)})


def test_strategy_returns_requested_hold():
    snapshot = make_snapshot()
    actions = FixedHoldStrategy().evaluate(snapshot)
    assert actions == (HoldAction("rem_0001", 30.0, "test hold"),)


def test_strategy_without_evaluate_cannot_be_created():
    class Incomplete(DecisionController):
        name = "incomplete"

    with pytest.raises(TypeError, match="evaluate"):
        Incomplete()


def test_hold_action_accepts_integer_seconds():
    action = HoldAction("rem_0001", 45, "connection protection")
    assert action.duration_s == 45


@pytest.mark.parametrize(
    ("duration", "message"),
    [
        (0.0, "> 0"),
        (-1.0, "> 0"),
        (math.nan, "> 0"),
        (math.inf, "> 0"),
        (True, "number of seconds"),
        ("30", "number of seconds"),
    ],
)
def test_hold_action_rejects_bad_duration(duration, message):
    with pytest.raises(ValueError, match=message):
        HoldAction("rem_0001", duration, "test hold")


@pytest.mark.parametrize(
    ("train_id", "reason", "field_name"),
    [
        ("", "test hold", "train_id"),
        (None, "test hold", "train_id"),
        ("rem_0001", "   ", "reason"),
    ],
)
def test_hold_action_rejects_missing_text(train_id, reason, field_name):
    with pytest.raises(ValueError, match=field_name):
        HoldAction(train_id, 30.0, reason)
