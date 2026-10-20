# AI contribution: 50% or less AI-generated
"""Passenger identity and state for US-1.3, Task 1.3.1 (#17).

Origin and destination are station identifiers. Platform locations, train
membership and state transitions belong to the movement components (#18, #100).
"""

from dataclasses import dataclass
from enum import StrEnum


class PassengerState(StrEnum):
    """Where a passenger is in their modelled journey."""

    CREATED = "created"
    WALKING = "walking"
    WAITING = "waiting"
    ON_BOARD = "on_board"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class Passenger:
    """A validated passenger snapshot with a stable identity.

    Movement components can use ``dataclasses.replace`` to change state while
    preserving identity. This keeps invalid direct mutations out of the model.
    """

    passenger_id: str
    origin: str
    destination: str
    state: PassengerState = PassengerState.CREATED

    def __post_init__(self) -> None:
        for name in ("passenger_id", "origin", "destination"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Passenger.{name} must be a non-empty string")
        if self.origin == self.destination:
            raise ValueError("Passenger.destination must differ from origin")
        if not isinstance(self.state, PassengerState):
            raise ValueError("Passenger.state must be a PassengerState")
