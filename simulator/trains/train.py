from dataclasses import dataclass
import math

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

        if not (
            math.isfinite(self.arrival_s)
            and math.isfinite(self.departure_s)
        ):
            raise ValueError("Stop times must be finite")

        if self.arrival_s < 0 or self.departure_s < self.arrival_s:
            raise ValueError("Invalid stop arrival/departure times")

@dataclass(slots=True)
class Train:
    """One train with persistent identity throughout its trip"""

    id: str
    capacity: int
    schedule: tuple[ScheduledStop, ...]

    onboard_load: int = 0
    current_delay: float = 0.0
    layover_slack: float = 0.0
    current_stop_index: int = 0

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Train ID cannot be empty")

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

        for previous, current in zip(self.schedule, self.schedule[1:]):
            if current.arrival_s < previous.departure_s:
                raise ValueError("Train stops must be chronological")

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

    def update_delay(self, actual_s: float, scheduled_s: float,) -> None:
        """Update schedule deviation: positive means late"""
        if not math.isfinite(actual_s) or not math.isfinite(scheduled_s):
            raise ValueError("Times must be finite")

        self.current_delay = actual_s - scheduled_s

    def advance_stop(self) -> bool:
        """Move to the next planned stop, if one exists"""
        if self.current_stop_index + 1 >= len(self.schedule):
            return False

        self.current_stop_index += 1
        return True
    
