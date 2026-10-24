# AI contribution: 50% or more AI-generated
"""Deterministic dwell calculation, independent of passenger event handling."""

import math
from dataclasses import dataclass
from numbers import Integral


@dataclass(frozen=True)
class DwellModel:
    """Additive boarding/alighting model with explicitly configured coefficients.

    dwell = base_dwell_s + boarding_s_per_passenger * boarded_count
            + alighting_s_per_passenger * alighted_count

    The base covers door operation and other fixed stop time. Passenger terms
    represent sequential service; parallel door flows are not modeled. Rates
    are effective seconds per passenger across the train, not per-door rates.
    Coefficients must be supplied by the caller: no calibrated defaults are
    assumed. Crowding penalties belong to task 1.4.2.
    """

    base_dwell_s: float
    boarding_s_per_passenger: float
    alighting_s_per_passenger: float

    def __post_init__(self) -> None:
        for name in (
            "base_dwell_s",
            "boarding_s_per_passenger",
            "alighting_s_per_passenger",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"{name} must be finite and non-negative")

    def compute(self, *, boarded_count: int, alighted_count: int) -> float:
        """Return dwell seconds from actual passenger counts for one stop.

        Zero passenger movements return the base dwell. A positive coefficient
        makes dwell strictly increase with its corresponding passenger count;
        zero disables that contribution. Counts exclude passengers left behind.
        """
        for name, count in (
            ("boarded_count", boarded_count),
            ("alighted_count", alighted_count),
        ):
            if isinstance(count, bool) or not isinstance(count, Integral) or count < 0:
                raise ValueError(f"{name} must be a non-negative integer")

        try:
            dwell_s = float(
                self.base_dwell_s
                + self.boarding_s_per_passenger * boarded_count
                + self.alighting_s_per_passenger * alighted_count
            )
        except OverflowError as exc:
            raise ValueError("Computed dwell must be finite") from exc
        if not math.isfinite(dwell_s):
            raise ValueError("Computed dwell must be finite")
        return dwell_s
