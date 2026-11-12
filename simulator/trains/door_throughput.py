# AI contribution: 50% or more AI-generated
"""REM fixed-window boarding budget, Mathematical Foundations section 4 (#24).

This is a per-stop aggregate bound, not a continuous passenger service clock.
Rates must be explicitly supplied from measurements or documented assumptions.
"""

import math
from dataclasses import dataclass
from fractions import Fraction
from numbers import Integral, Real

# One message for every invalid scheduled dwell, so the type, overflow and
# range checks in DoorThroughput.budget report the same error.
_INVALID_DWELL = "scheduled_dwell_s must be finite and non-negative"


@dataclass(frozen=True)
class DoorThroughput:
    """Configured passengers/second/door and platform-side boarding door count.

    There are no calibrated defaults. Invalid or non-positive values raise
    ValueError. Each visit receives a fresh scheduled-dwell budget; holds and
    clearance waits do not increase it, following the wiki's fixed-window form.
    """

    passengers_per_second_per_door: float
    doors: int

    def __post_init__(self) -> None:
        rate = self.passengers_per_second_per_door
        try:
            valid = isinstance(rate, Real) and not isinstance(rate, bool)
            normalized = float(rate) if valid else math.nan
        except OverflowError:
            normalized = math.nan
        if not math.isfinite(normalized) or normalized <= 0:
            raise ValueError(
                "passengers_per_second_per_door must be finite and positive"
            )
        if (
            isinstance(self.doors, bool)
            or not isinstance(self.doors, Integral)
            or self.doors <= 0
        ):
            raise ValueError("doors must be a positive integer")
        object.__setattr__(self, "passengers_per_second_per_door", normalized)
        object.__setattr__(self, "doors", int(self.doors))

    def budget(self, scheduled_dwell_s: float) -> int:
        """Return whole passengers fitting the scheduled window, rounding down.

        Decimal representations avoid losing a passenger to binary multiplication
        at an exact threshold (for example 0.3 passengers/s over 10 seconds).
        Zero dwell yields zero; invalid dwell raises ValueError.
        """
        if isinstance(scheduled_dwell_s, bool) or not isinstance(
            scheduled_dwell_s, Real
        ):
            raise ValueError(_INVALID_DWELL)
        try:
            dwell = float(scheduled_dwell_s)
        except OverflowError as exc:
            raise ValueError(_INVALID_DWELL) from exc
        if not math.isfinite(dwell) or dwell < 0:
            raise ValueError(_INVALID_DWELL)
        return int(
            Fraction(str(self.passengers_per_second_per_door))
            * Fraction(str(dwell))
            * self.doors
        )
