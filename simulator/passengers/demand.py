# AI contribution: 50% or more AI-generated
"""

Time bands use simulation seconds. Rates are passengers per minute and are
constant within each band. Demand is zero in gaps and outside configured bands.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass


def _nonnegative_number(value: float, name: str) -> float:
    """Validate a time or rate without accepting booleans as numbers."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be a finite number >= 0")
    try:
        number = float(value)
    except OverflowError as error:
        raise ValueError(f"{name} must be a finite number >= 0") from error
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be a finite number >= 0")
    return number


@dataclass(frozen=True, slots=True)
class DemandPeriod:
    """Demand rate over the half-open interval ``[start_s, end_s)``."""

    start_s: float
    end_s: float
    passengers_per_minute: float

    def __post_init__(self) -> None:
        for name in ("start_s", "end_s", "passengers_per_minute"):
            number = _nonnegative_number(getattr(self, name), f"DemandPeriod.{name}")
            object.__setattr__(self, name, number)
        if self.end_s <= self.start_s:
            raise ValueError("DemandPeriod.end_s must be greater than start_s")


@dataclass(frozen=True, slots=True)
class DemandProfile:
    """An immutable sequence of ordered, non-overlapping demand periods."""

    periods: Sequence[DemandPeriod] = ()

    def __post_init__(self) -> None:
        if (
            isinstance(self.periods, str | bytes)
            or not isinstance(self.periods, Sequence)
            or any(not isinstance(period, DemandPeriod) for period in self.periods)
        ):
            raise ValueError("DemandProfile.periods must be a sequence of DemandPeriod")
        periods = tuple(self.periods)
        for previous, current in zip(periods, periods[1:], strict=False):
            if current.start_s < previous.end_s:
                raise ValueError(
                    "DemandProfile.periods must be ordered and non-overlapping"
                )
        object.__setattr__(self, "periods", periods)

    def expected_count(self, start_s: float, end_s: float) -> float:
        """Expected passengers in ``[start_s, end_s)``, integrating every band.

        Each band's contribution is rate * overlap_seconds / 60. A zero-length
        window has zero demand. This computes volume, not platform arrival times.
        """
        start = _nonnegative_number(start_s, "start_s")
        end = _nonnegative_number(end_s, "end_s")
        if end < start:
            raise ValueError("end_s must be >= start_s")
        try:
            expected = math.fsum(
                period.passengers_per_minute
                / 60.0
                * max(0.0, min(end, period.end_s) - max(start, period.start_s))
                for period in self.periods
            )
        except OverflowError as error:
            raise ValueError("expected passenger count must be finite") from error
        if not math.isfinite(expected):
            raise ValueError("expected passenger count must be finite")
        return expected
