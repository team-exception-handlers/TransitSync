# AI contribution: Below 50% AI-generated
"""Unit tests for the no-control baseline strategy (US-2.3, #46)."""

import pytest

from simulator.control.interface import (
    IncomingTransfer,
    ObservationSnapshot,
    PlatformState,
    TrainState,
)
from simulator.control.strategies.no_control import NoControlStrategy

LATE_FULL_TRAIN = TrainState(
    train_id="rem_0001",
    line_id="rem",
    next_platform_id="rem_mcgill_0",
    predicted_arrival_s=400.0,
    scheduled_departure_s=300.0,
    delay_s=180.0,
    onboard_load=780,
    capacity=780,
)
BIG_TRANSFER = IncomingTransfer(
    group_id="xfer-group-000001",
    platform_id="rem_gare_centrale_0",
    passenger_count=250,
    first_arrival_s=125.0,
    last_arrival_s=200.0,
)


def snapshot(trains=(), transfers=()) -> ObservationSnapshot:
    return ObservationSnapshot(
        time_s=120.0,
        train_id="rem_0001",
        station_id="gare_centrale",
        platform_id="rem_gare_centrale_0",
        scheduled_departure_s=130.0,
        trains=trains,
        platforms=(PlatformState("rem_gare_centrale_0", 0, None),),
        incoming_transfers=transfers,
    )


@pytest.mark.parametrize(
    "observation",
    [
        snapshot(),
        snapshot(trains=(LATE_FULL_TRAIN,)),
        # Many passengers about to arrive would tempt any holding rule
        snapshot(transfers=(BIG_TRANSFER,)),
    ],
)
def test_no_control_never_requests_a_hold(observation):
    assert NoControlStrategy().evaluate(observation) == ()


def test_no_control_is_registered_under_its_name():
    assert NoControlStrategy.name == "no_control"
