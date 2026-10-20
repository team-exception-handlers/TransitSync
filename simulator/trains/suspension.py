# AI contribution: 50% or more AI-generated
"""Dispatch restrictions for US-1.5 #27; all times are seconds."""

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LineSuspension:
    """Halt new trip departures on one line in [start_s, end_s)."""

    line_id: str
    start_s: float
    end_s: float

    def __post_init__(self) -> None:
        if not isinstance(self.line_id, str) or not self.line_id.strip():
            raise ValueError("Suspension line ID cannot be empty")
        for value in (self.start_s, self.end_s):
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError("Suspension times must be finite and non-negative")
        if self.end_s <= self.start_s:
            raise ValueError("Suspension must end after it starts")


def dispatch_ready_s(
    line_id: str, time_s: float, suspensions: Sequence[LineSuspension]
) -> float:
    """Earliest allowed dispatch in seconds, including overlapping intervals."""
    ready_s = time_s
    for suspension in sorted(suspensions, key=lambda item: item.start_s):
        if (
            suspension.line_id == line_id
            and suspension.start_s <= ready_s < suspension.end_s
        ):
            ready_s = suspension.end_s
    return ready_s
