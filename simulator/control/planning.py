# AI contribution: 50% or more AI-generated
"""Immutable forward visits for coordinated planning (US-2.6 #61).

Value Objects extend the controller view without exposing mutable trains.
Times are simulation seconds; a visit key distinguishes return trips and
repeated platforms. Predictions include existing delay, never a proposed hold.
"""

from dataclasses import dataclass

from simulator.control.validation import finite_number

VisitKey = tuple[str, int, int]


@dataclass(frozen=True, slots=True)
class FutureVisit:
    """One remaining stop, including the current dwelling stop.

    ``can_hold`` is false after a decision or at an inbound turnaround, where
    the engine skips departure. ``recovery_s`` is unused terminal slack before
    this visit. It absorbs additional delay once, at the trip boundary.
    ``arrived`` fixes an observed arrival; ``earliest_arrival_s`` carries the
    simulator's known platform boundary without revealing a mutable cursor.
    """

    train_id: str
    trip_index: int
    stop_index: int
    station_id: str
    platform_id: str
    arrival_s: float
    departure_s: float
    scheduled_arrival_s: float
    scheduled_departure_s: float
    can_hold: bool = True
    skips_departure: bool = False
    recovery_s: float = 0.0
    arrived: bool = False
    earliest_arrival_s: float = 0.0

    @property
    def key(self) -> VisitKey:
        """Stable identity within this vehicle's complete timetable."""
        return (self.train_id, self.trip_index, self.stop_index)


@dataclass(frozen=True, slots=True)
class RollingHorizonSettings:
    """Forward window in seconds and a bound on candidate evaluations.

    The assumed 300 s default is a modelling choice, not a safety limit.
    Larger grids use bounded approximate search without dropping stations.
    The planner marks approximate results explicitly; a budget too small to
    explore every station raises an error before candidate scoring begins.
    """

    window_s: float = 300.0
    max_combinations: int = 100_000

    def __post_init__(self) -> None:
        window = finite_number("RollingHorizonSettings.window_s", self.window_s)
        if window <= 0:
            raise ValueError("RollingHorizonSettings.window_s must be > 0")
        count = self.max_combinations
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("RollingHorizonSettings.max_combinations must be >= 1")
        object.__setattr__(self, "window_s", window)

    def to_dict(self) -> dict[str, float | int]:
        """Save both search limits in scenario files and run manifests."""
        return {"window_s": self.window_s, "max_combinations": self.max_combinations}
