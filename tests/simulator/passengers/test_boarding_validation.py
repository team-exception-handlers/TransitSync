# AI contribution: 50% or more AI-generated
"""Initial manifest and foreign-event boundaries for task #100.

The queue never invents onboard load: initial tracked passengers must already
occupy seats on a known vehicle. Fixtures are built before pytest.raises so a
failure identifies the constructor or method under test, not a fixture helper.
"""

import pytest

from simulator.engine.events import PassengerArrival
from simulator.passengers import Passenger, PassengerState
from simulator.passengers.platform_queue import PlatformQueue
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


@pytest.mark.parametrize(
    "initial, state, destination, message",
    [
        ({"missing-train": ["p"]}, PassengerState.ON_BOARD, "B", "unknown train"),
        ({"metro": "p"}, PassengerState.ON_BOARD, "B", "sequences"),
        ({"metro": ["unknown"]}, PassengerState.ON_BOARD, "B", "known and unique"),
        ({"metro": [None]}, PassengerState.ON_BOARD, "B", "strings"),
        ({}, PassengerState.ON_BOARD, "B", "every ON_BOARD"),
        ({"metro": ["p", "p"]}, PassengerState.ON_BOARD, "B", "known and unique"),
        ({"metro": ["p", "q", "r"]}, PassengerState.ON_BOARD, "B", "exceeds"),
        ({"metro": ["p"]}, PassengerState.WALKING, "B", "must be ON_BOARD"),
        ({"metro": ["p"]}, PassengerState.ON_BOARD, "Z", "not on the train route"),
    ],
)
def test_invalid_initial_manifests_fail_before_moving_passengers(
    initial, state, destination, message
):
    """Reject inconsistent identity, load, state or destination configuration.

    The vehicle has two aggregate passengers: duplicate tracked IDs cannot hide
    behind an over-capacity failure. Validation must leave this load untouched.
    """
    people = {"p": Passenger("p", "origin", destination, state)}
    metro = Train(
        "metro",
        3,
        (
            ScheduledStop("A", "P", 100, 120),
            ScheduledStop("B", "Q", 220, 240),
        ),
        onboard_load=2,
    )
    queue = PlatformQueue(("P",), passengers=people, initial_onboard=initial)
    vehicles = [metro]
    with pytest.raises(ValueError, match=message):
        TrainComponent(vehicles, passenger_queue=queue)
    assert metro.onboard_load == 2
    assert people["p"].state is state


@pytest.mark.parametrize("case", ["registry", "manifest", "missing_registry"])
def test_queue_constructor_rejects_invalid_tracking_inputs(case):
    """Bad mappings fail before a queue is attached to the train component.

    An ID key must match its snapshot, manifests must be mappings, and an
    initial onboard list requires the shared passenger dictionary.
    """
    people = {"wrong-key": Passenger("p", "A", "B")}
    kwargs = {"passengers": people}
    message = "passengers must map"
    if case == "manifest":
        kwargs = {"initial_onboard": []}
        message = "initial_onboard must map"
    elif case == "missing_registry":
        kwargs = {"initial_onboard": {"metro": ["p"]}}
        message = "requires passengers"
    with pytest.raises(ValueError, match=message):
        PlatformQueue(("P",), **kwargs)


@pytest.mark.parametrize(
    "state", [None, PassengerState.ON_BOARD, PassengerState.COMPLETED]
)
def test_foreign_and_already_onboard_or_completed_arrivals_are_ignored(state):
    """An unrelated arrival cannot duplicate an onboard identity or restart a trip."""
    people = {} if state is None else {"p": Passenger("p", "A", "B", state)}
    queue = PlatformQueue(("P",), passengers=people)
    event = PassengerArrival(time_s=10, passenger_id="p", group_id="g", platform_id="P")
    assert queue.arrive(event) is False
    assert queue.waiting_count("P") == 0


def test_duplicate_accepted_arrival_cannot_take_two_queue_positions():
    """Duplicate input raises clearly while preserving the original FIFO entry.

    The first arrival changes CREATED to WAITING. Retrying that same identity
    must not duplicate demand or reserve a second seat on a subsequent train.
    """
    people = {"p": Passenger("p", "A", "B")}
    queue = PlatformQueue(("P",), passengers=people)
    event = PassengerArrival(time_s=10, passenger_id="p", group_id="g", platform_id="P")
    assert queue.arrive(event) is True
    with pytest.raises(ValueError, match="Duplicate passenger arrival"):
        queue.arrive(event)
    assert queue.waiting_count("P") == 1
