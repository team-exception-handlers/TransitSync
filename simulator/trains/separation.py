"""Minimum event headway and deterministic delay propagation"""

import math
from dataclasses import dataclass
from collections.abc import Sequence

@dataclass(frozen=True, slots=True)
class TrainMovement:
    """One train's planned movement through a shared resource"""
    train_id: str
    scheduled_s: float
    generated_delay_s: float = 0.0

@dataclass(frozen = True, slots = True)
class SeparationResult:
    """Actual movement time and its delay breakdown"""
    train_id: str
    scheduled_s: float
    actual_s: float
    generated_delay_s: float
    inherited_delay_s: float

    @property
    def total_delay_s(self) -> float:
        return self.actual_s - self.scheduled_s

def enforce_minimum_gap(movements: Sequence[TrainMovement],minimum_gap_s: float,) -> list[SeparationResult]:
    """Apply gap in train order at one shared location. Movements are supplied in physical train order, from the leading train to the ones following."""

    if not math.isfinite(minimum_gap_s) or minimum_gap_s <= 0:
        raise ValueError("Minimum gap must be finite and positive")

    results: list[SeparationResult] = []
    previous_actual_s: float | None = None
    seen_ids: set[str] = set()
    previous_scheduled_s: float | None = None

    for movement in movements:
        if not movement.train_id or movement.train_id in seen_ids:
            raise ValueError("Train IDs must be unique and non-empty")

        if not(math.isfinite(movement.scheduled_s) and math.isfinite(movement.generated_delay_s)):
            raise ValueError("Movement times must be finite")

        if movement.scheduled_s < 0 or movement.generated_delay_s < 0:
            raise ValueError("Movement times must be non-negative")

        if (previous_scheduled_s is not None and movement.scheduled_s < previous_scheduled_s):
            raise ValueError("Movements must be in scheduled train order")

        seen_ids.add(movement.train_id)
        previous_scheduled_s = movement.scheduled_s

        requested_s = (movement.scheduled_s + movement.generated_delay_s)

        actual_s = requested_s

        if previous_actual_s is not None:
            actual_s = max(requested_s, previous_actual_s + minimum_gap_s,)

        inherited_delay_s = actual_s - requested_s
        results.append(SeparationResult(train_id = movement.train_id, scheduled_s = movement.scheduled_s, actual_s = actual_s, generated_delay_s = movement.generated_delay_s, inherited_delay_s = inherited_delay_s,))
        previous_actual_s = actual_s
    return results