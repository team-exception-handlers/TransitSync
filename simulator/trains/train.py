# AI contribution: 50% or more AI-generated

import math
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ScheduledStop:
    """A train's planned arrival and departure at one platform."""

    station_id: str
    platform_id: str
    arrival_s: float
    departure_s: float

    def __post_init__(self) -> None:
        if not self.station_id or not self.platform_id:
            raise ValueError("Station and platform IDs cannot be empty")

        if not (math.isfinite(self.arrival_s) and math.isfinite(self.departure_s)):
            raise ValueError("Stop times must be finite")

        if self.arrival_s < 0 or self.departure_s < self.arrival_s:
            raise ValueError("Invalid stop arrival/departure times")


def _check_chronological(stops: tuple[ScheduledStop, ...]) -> None:
    """Require each stop to arrive no earlier than the previous one departs."""
    for previous, current in zip(stops, stops[1:], strict=False):
        if current.arrival_s < previous.departure_s:
            raise ValueError("Train stops must be chronological")


@dataclass(slots=True)
class Train:
    """One vehicle with persistent identity across scheduled trips, in seconds."""

    id: str
    capacity: int
    schedule: tuple[ScheduledStop, ...]

    onboard_load: int = 0
    current_delay: float = 0.0
    layover_slack: float = 0.0
    current_stop_index: int = 0
    generated_delay_s: float = 0.0
    inherited_delay_s: float = 0.0
    line_id: str = ""
    return_trips: tuple[tuple[ScheduledStop, ...], ...] = ()
    current_trip_index: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Train ID cannot be empty")
        if not isinstance(self.line_id, str):
            raise ValueError("Line ID must be a string")

        if self.capacity <= 0:
            raise ValueError("Train capacity must be positive")

        if not 0 <= self.onboard_load <= self.capacity:
            raise ValueError("Onboard load exceeds train capacity")

        if not self.schedule:
            raise ValueError("Train must have at least one stop")

        if not math.isfinite(self.current_delay):
            raise ValueError("Delay must be finite")

        if not math.isfinite(self.layover_slack) or self.layover_slack < 0:
            raise ValueError("Layover slack must be finite and non-negative")

        _check_chronological(self.schedule)
        self._check_return_trips()
        self._check_delay_breakdown()

    def _check_return_trips(self) -> None:
        """Validate complete trip schedules and configured turnaround budgets."""
        previous_trip = self.schedule
        for trip in self.return_trips:
            if not trip:
                raise ValueError("Return trips cannot be empty")
            _check_chronological(trip)
            terminal, origin = previous_trip[-1], trip[0]
            if origin.station_id != terminal.station_id:
                raise ValueError("Return trip must start at the previous terminus")
            gap_s = origin.arrival_s - terminal.departure_s
            if gap_s <= 0 or gap_s < self.layover_slack:
                raise ValueError("Return trip gap must be positive and cover slack")
            previous_trip = trip

    def _check_delay_breakdown(self) -> None:
        """Require delay components to be valid and add up to the total delay."""
        if not all(
            math.isfinite(value) and value >= 0
            for value in (
                self.generated_delay_s,
                self.inherited_delay_s,
            )
        ):
            raise ValueError("Delay components must be non-negative and finite")

        if not math.isclose(
            max(0.0, self.current_delay),
            self.generated_delay_s + self.inherited_delay_s,
            abs_tol=1e-9,
        ):
            raise ValueError("Initial delay breakdown does not match total delay")

    @property
    def available_capacity(self) -> int:
        return self.capacity - self.onboard_load

    @property
    def current_stop(self) -> ScheduledStop:
        return self.schedule[self.current_stop_index]

    def board(self, count: int) -> None:
        """Add passengers without exceeding capacity."""
        if isinstance(count, bool) or not isinstance(count, int):
            raise ValueError("Boarding count must be an integer")

        if count < 0 or count > self.available_capacity:
            raise ValueError("Invalid boarding count")

        self.onboard_load += count

    def alight(self, count: int) -> None:
        """Remove passengers from the train"""
        if isinstance(count, bool) or not isinstance(count, int):
            raise ValueError("Alighting count must be an integer")

        if count < 0 or count > self.onboard_load:
            raise ValueError("Invalid alighting count")

        self.onboard_load -= count

    def update_delay(
        self, actual_s: float, scheduled_s: float, *, inherited_wait_s: float = 0.0
    ) -> None:
        """Update schedule deviation: positive means late"""

        values = (actual_s, scheduled_s, inherited_wait_s)

        if not all(math.isfinite(value) for value in values):
            raise ValueError("Delay values must be finite")

        if inherited_wait_s < 0:
            raise ValueError("Inherited waiting time cannot be negative")

        previous_delay = max(0.0, self.current_delay)
        new_delay = max(0.0, actual_s - scheduled_s)

        change = new_delay - previous_delay

        if change > 0:
            inherited = min(change, inherited_wait_s)

            self.inherited_delay_s += inherited
            self.generated_delay_s += change - inherited

        elif change < 0:
            recovered = -change

            inherited_recovery = min(self.inherited_delay_s, recovered)

            self.inherited_delay_s -= inherited_recovery
            recovered -= inherited_recovery

            self.generated_delay_s = max(0.0, self.generated_delay_s - recovered)

        self.current_delay = actual_s - scheduled_s

    def advance_stop(self) -> bool:
        """Move to the next planned stop, if one exists"""
        if self.current_stop_index + 1 >= len(self.schedule):
            return False

        self.current_stop_index += 1
        return True

    def begin_return_trip(self) -> float | None:
        """US-1.2 #16, Mathematical Foundations §6; return ready time in seconds.

        The gap between trips includes the recoverable ``layover_slack``.
        Any remaining gap is mandatory turnaround time. Consume slack once
        per trip boundary, retaining this vehicle and its capacity/load.
        """
        if self.current_trip_index >= len(self.return_trips):
            return None
        if self.current_stop_index != len(self.schedule) - 1:
            raise ValueError("Return trip can only begin at the terminus")
        self.schedule = self.return_trips[self.current_trip_index]
        self.current_trip_index += 1
        self.current_stop_index = 0
        self.current_delay = max(0.0, self.current_delay - self.layover_slack)
        # Recover inherited delay first; the two components still sum to total.
        self.generated_delay_s = min(self.generated_delay_s, self.current_delay)
        self.inherited_delay_s = self.current_delay - self.generated_delay_s
        return self.current_stop.arrival_s + self.current_delay
