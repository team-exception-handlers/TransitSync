# AI contribution: No substantial AI-generated code
"""Queue passengers when a transfer corridor gets crowded.

This implements US-1.3, Task 1.3.4 (#20), following the queueing model in
Mathematical Foundations section 5. Times are in seconds, while corridor
capacity is measured in passengers per minute.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CorridorPassage:
    """When one passenger arrived, passed through and how long they waited."""

    passenger_id: str
    arrival_s: float
    passage_s: float
    queue_delay_s: float


class CorridorQueue:
    """Let passengers through in arrival order without exceeding capacity.

    Passengers use evenly spaced passage slots. Quiet periods do not build up
    extra capacity, so the first passenger to arrive at an empty corridor can
    pass immediately.
    """

    def __init__(self, capacity_per_minute: float) -> None:
        if (
            isinstance(capacity_per_minute, bool)
            or not isinstance(capacity_per_minute, int | float)
            or not math.isfinite(capacity_per_minute)
            or capacity_per_minute <= 0
        ):
            raise ValueError("capacity_per_minute must be a finite number > 0")
        self.capacity_per_minute = float(capacity_per_minute)
        self._slot_s = 60.0 / self.capacity_per_minute
        self._next_passage_s = 0.0
        self._last_arrival_s = 0.0

    def admit(self, passenger_id: str, arrival_s: float) -> CorridorPassage:
        """Add one passenger and return when they pass and how long they wait.

        Passengers must arrive in time order, just as they do in the simulator's
        event queue.
        """
        arrival = self._validate_arrival(arrival_s)
        passage_s = max(arrival, self._next_passage_s)
        if math.isclose(passage_s, arrival, rel_tol=0.0, abs_tol=1e-9):
            passage_s = arrival
        result = CorridorPassage(
            passenger_id=passenger_id,
            arrival_s=arrival,
            passage_s=passage_s,
            queue_delay_s=passage_s - arrival,
        )
        self._last_arrival_s = arrival
        self._next_passage_s = passage_s + self._slot_s
        return result

    def _validate_arrival(self, arrival_s: float) -> float:
        if isinstance(arrival_s, bool) or not isinstance(arrival_s, int | float):
            raise ValueError("arrival_s must be a number of seconds")
        if not math.isfinite(arrival_s) or arrival_s < 0:
            raise ValueError(f"arrival_s must be finite and >= 0, got {arrival_s}")
        arrival = float(arrival_s)
        if arrival < self._last_arrival_s:
            raise ValueError(
                f"arrival_s must be >= the previous arrival "
                f"({self._last_arrival_s}), got {arrival}"
            )
        return arrival
