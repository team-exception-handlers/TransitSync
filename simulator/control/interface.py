# AI contribution: Below 50% AI-generated
"""Controller interface: what a strategy receives and what it may return.

Implements US-2.1, Task 2.1.1 (#37). Design pattern: Strategy, with every
holding rule implementing ``DecisionController``; the snapshot types are
frozen Value Objects. Strategies are read-only (Mathematical Foundations), so
a strategy gets a snapshot it cannot change and returns ``HoldAction``
requests that the rule checking layer (US-2.5) may shorten or refuse.
Times are in seconds of simulation clock.
"""

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar


def _check_text(label: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class HoldAction:
    """A request to hold ``train_id`` at its platform for ``duration_s`` > 0.

    ``reason`` is copied to the ``Hold`` event. A strategy that does not want
    to hold returns no action. Raises ``ValueError`` naming a bad field.
    """

    train_id: str
    duration_s: float
    reason: str

    def __post_init__(self) -> None:
        _check_text("HoldAction.train_id", self.train_id)
        _check_text("HoldAction.reason", self.reason)
        # bool is a subclass of int, so it is excluded explicitly
        duration = self.duration_s
        if isinstance(duration, bool) or not isinstance(duration, int | float):
            raise ValueError("HoldAction.duration_s must be a number of seconds")
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError(
                f"HoldAction.duration_s must be finite and > 0, got {duration}"
            )


@dataclass(frozen=True, slots=True)
class TrainState:
    """One train as a strategy sees it; times may carry prediction error (#39).

    The next-stop fields are ``None`` when the train has no further stop.
    """

    train_id: str
    line_id: str
    next_platform_id: str | None
    predicted_arrival_s: float | None
    scheduled_departure_s: float | None
    delay_s: float
    onboard_load: int
    capacity: int


@dataclass(frozen=True, slots=True)
class PlatformState:
    """Waiting passengers; ``last_departure_s`` is ``None`` before the first."""

    platform_id: str
    waiting_count: int
    last_departure_s: float | None


@dataclass(frozen=True, slots=True)
class IncomingTransfer:
    """A transfer group from one train arrival, still walking (pulsed arrivals)."""

    group_id: str
    platform_id: str
    passenger_count: int
    first_arrival_s: float
    last_arrival_s: float


@dataclass(frozen=True, slots=True)
class ObservationSnapshot:
    """Everything a strategy sees when ``train_id`` is ready to leave.

    ``scheduled_departure_s`` is this stop's timetable departure in seconds,
    including at a final stop. ``TrainState`` describes each train's next stop.
    Raises ``ValueError`` if a collection is not a tuple.
    """

    time_s: float
    train_id: str
    station_id: str
    platform_id: str
    scheduled_departure_s: float
    trains: tuple[TrainState, ...]
    platforms: tuple[PlatformState, ...]
    incoming_transfers: tuple[IncomingTransfer, ...]

    def __post_init__(self) -> None:
        # Frozen only stops reassignment; a list or deque could still be changed
        # in place, so every collection must be an immutable tuple
        for name in ("trains", "platforms", "incoming_transfers"):
            if not isinstance(getattr(self, name), tuple):
                raise ValueError(f"ObservationSnapshot.{name} must be a tuple")


class DecisionController(ABC):
    """Interface every control strategy implements.

    ``name`` selects the strategy in a scenario.
    """

    name: ClassVar[str]

    @abstractmethod
    def evaluate(self, observation: ObservationSnapshot) -> tuple[HoldAction, ...]:
        """Return the holds requested at this decision point, possibly none."""
