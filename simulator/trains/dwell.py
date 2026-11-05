# AI contribution: 50% or more AI-generated
"""Deterministic dwell calculation, independent of passenger event handling."""

import math
from dataclasses import dataclass
from numbers import Integral


@dataclass(frozen=True)
class DwellModel:
    """Additive boarding/alighting model with explicitly configured coefficients.

    service = boarding_s_per_passenger * boarded_count
              + alighting_s_per_passenger * alighted_count
    dwell = base_dwell_s + service * (1 + crowding_strength * load_ratio**4)

    The base covers door operation and other fixed stop time. Passenger terms
    represent sequential service; parallel door flows are not modeled. Rates
    are effective seconds per passenger across the train, not per-door rates.
    Coefficients must be supplied by the caller: no calibrated defaults are
    assumed. Crowding strength is dimensionless: at capacity it is the extra
    fraction of passenger service time. Zero disables crowding. The quartic
    curve is a modeling choice, not an empirically calibrated relationship.
    """

    base_dwell_s: float
    boarding_s_per_passenger: float
    alighting_s_per_passenger: float
    crowding_strength: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "base_dwell_s",
            "boarding_s_per_passenger",
            "alighting_s_per_passenger",
            "crowding_strength",
        ):
            value = getattr(self, name)
            try:
                valid = (
                    not isinstance(value, bool)
                    and isinstance(value, (int, float))
                    and math.isfinite(value)
                    and value >= 0
                )
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError(f"{name} must be finite and non-negative")

    def compute(
        self,
        *,
        boarded_count: int,
        alighted_count: int,
        onboard_load: int | None = None,
        capacity: int | None = None,
    ) -> float:
        """Return dwell seconds from actual passenger counts for one stop.

        Zero passenger movements return the base dwell. A positive coefficient
        makes dwell strictly increase with its corresponding passenger count;
        zero disables that contribution. Counts exclude passengers left behind.
        For crowding, supply load after alighting and boarding and positive
        train capacity. Both are required when crowding is enabled; if supplied
        when disabled they are still validated. Full capacity is finite.
        """
        for name, count in (
            ("boarded_count", boarded_count),
            ("alighted_count", alighted_count),
        ):
            if isinstance(count, bool) or not isinstance(count, Integral) or count < 0:
                raise ValueError(f"{name} must be a non-negative integer")

        load_ratio = self._load_ratio(onboard_load, capacity)
        # Integral includes NumPy scalars: convert before arithmetic to prevent
        # fixed-width overflow from returning negative dwell.
        boarded_count, alighted_count = int(boarded_count), int(alighted_count)
        try:
            service_s = (
                self.boarding_s_per_passenger * boarded_count
                + self.alighting_s_per_passenger * alighted_count
            )
            # Evaluate the bounded load term first to avoid unnecessary overflow.
            penalty = self.crowding_strength * load_ratio**4
            dwell_s = float(self.base_dwell_s + service_s + service_s * penalty)
        except OverflowError as exc:
            raise ValueError("Computed dwell must be finite") from exc
        if not math.isfinite(dwell_s):
            raise ValueError("Computed dwell must be finite")
        return dwell_s

    def _load_ratio(self, onboard_load: int | None, capacity: int | None) -> float:
        if onboard_load is None and capacity is None and self.crowding_strength == 0:
            return 0.0
        for name, count, minimum in (
            ("onboard_load", onboard_load, 0),
            ("capacity", capacity, 1),
        ):
            if (
                isinstance(count, bool)
                or not isinstance(count, Integral)
                or count < minimum
            ):
                raise ValueError(f"{name} must be an integer >= {minimum}")
        onboard_load, capacity = int(onboard_load), int(capacity)
        if onboard_load > capacity:
            raise ValueError("onboard_load must not exceed capacity")
        return onboard_load / capacity
