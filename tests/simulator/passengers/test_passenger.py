# AI contribution: 50% or more AI-generated
"""Passenger model tests (US-1.3, Task 1.3.1, #17)."""

from dataclasses import FrozenInstanceError, replace

import pytest

from simulator.passengers.passenger import Passenger, PassengerState


def test_passenger_has_identity_origin_destination_and_initial_state():
    passenger = Passenger("p-1", " mcgill ", "bonaventure ")

    assert passenger.passenger_id == "p-1"
    assert passenger.origin == "mcgill"
    assert passenger.destination == "bonaventure"
    assert passenger.state is PassengerState.CREATED


@pytest.mark.parametrize(
    "name,invalid",
    [
        ("passenger_id", ""),
        ("origin", "   "),
        ("destination", None),
        ("passenger_id", 7),
    ],
)
def test_invalid_identifier_is_rejected_naming_the_field(name, invalid):
    values = {
        "passenger_id": "p-1",
        "origin": "mcgill",
        "destination": "bonaventure",
        name: invalid,
    }

    with pytest.raises(ValueError, match=name):
        Passenger(**values)


@pytest.mark.parametrize(
    "origin,destination", [("mcgill", "mcgill"), (" mcgill ", "mcgill ")]
)
def test_destination_must_differ_from_origin(origin, destination):
    with pytest.raises(ValueError, match="destination"):
        Passenger("p-1", origin, destination)


@pytest.mark.parametrize("invalid", [None, "created"])
def test_state_must_be_a_passenger_state(invalid):
    with pytest.raises(ValueError, match="state"):
        Passenger("p-1", "mcgill", "bonaventure", invalid)


def test_state_changes_preserve_identity_and_leave_the_previous_snapshot_intact():
    passenger = Passenger("p-1", "mcgill", "bonaventure")
    waiting = replace(passenger, state=PassengerState.WAITING)

    assert waiting == Passenger("p-1", "mcgill", "bonaventure", PassengerState.WAITING)
    assert passenger.state is PassengerState.CREATED
    with pytest.raises(FrozenInstanceError):
        passenger.passenger_id = "p-2"
