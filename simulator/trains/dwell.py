# AI contribution: 50% or more AI-generated
"""Deterministic dwell calculation, independent of passenger event handling."""

import math
from dataclasses import dataclass
from numbers import Integral, Real


@dataclass(frozen=True)
class DwellModel:
    """Demand-dependent Metro dwell with explicitly configured coefficients.

    service = boarding_s_per_passenger * boarded_count
              + alighting_s_per_passenger * alighted_count
    dwell = base_dwell_s + service * (1 + crowding_strength * load_ratio**exponent)

    Use this model only for Metro trains. REM doors close on a timer, so REM
    dwell stays fixed at its scheduled value; disabling crowding alone does not
    disable this model's boarding/alighting terms. The caller selects the model
    by network: this standalone calculation has no train or network identity.

    The base covers door operation and other fixed stop time. Passenger terms
    represent sequential service; parallel door flows are not modeled. Rates
    are effective seconds per passenger across the train, not per-door rates.
    Coefficients must be supplied by the caller: no calibrated defaults are
    assumed. Crowding strength is dimensionless: at capacity it is the extra
    fraction of passenger service time. Zero disables crowding. The exponent
    must exceed one to give sharper growth near capacity; its default of four
    is a modeling choice, not an empirically calibrated relationship.
    """

    base_dwell_s: float
    boarding_s_per_passenger: float
    alighting_s_per_passenger: float
    crowding_strength: float = 0.0
    crowding_exponent: float = 4.0

    def __post_init__(self) -> None:
        for name in (
            "base_dwell_s",
            "boarding_s_per_passenger",
            "alighting_s_per_passenger",
            "crowding_strength",
            "crowding_exponent",
        ):
            value = getattr(self, name)
            try:
                # Normalize real scalars too, so NumPy coefficients cannot
                # reintroduce fixed-width arithmetic during computation.
                normalized = float(value) if isinstance(value, Real) else math.nan
                valid = (
                    not isinstance(value, bool)
                    and math.isfinite(normalized)
                    and normalized >= 0
                )
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError(f"{name} must be finite and non-negative")
            object.__setattr__(self, name, normalized)
        if self.crowding_exponent <= 1:
            raise ValueError("crowding_exponent must be greater than one")

    def compute(
        self,
        *,
        boarded_count: int,
        alighted_count: int,
        onboard_load: int | None = None,
        capacity: int | None = None,
    ) -> float:
        """Return dwell seconds from actual passenger counts for one stop.

        Zero passenger movements return the base dwell. At a fixed load ratio,
        positive coefficients increase dwell with their passenger counts; zero
        disables that contribution. Counts exclude passengers left behind.
        Supply final load after alighting and boarding and positive capacity.
        Arrival load is inferred as final - boarded + alighted; crowding uses
        the larger of arrival and final load, assuming alighting precedes
        boarding. Counts and loads must describe a possible stop. Load/capacity
        are required when crowding is enabled; if supplied when disabled they
        are still validated. Full capacity has no singularity.
        """
        for name, count in (
            ("boarded_count", boarded_count),
            ("alighted_count", alighted_count),
        ):
            if isinstance(count, bool) or not isinstance(count, Integral) or count < 0:
                raise ValueError(f"{name} must be a non-negative integer")

        # Integral includes NumPy scalars: convert before arithmetic to prevent
        # fixed-width overflow from returning negative dwell.
        boarded_count, alighted_count = int(boarded_count), int(alighted_count)
        load_ratio = self._load_ratio(
            onboard_load, capacity, boarded_count, alighted_count
        )
        try:
            service_s = (
                self.boarding_s_per_passenger * boarded_count
                + self.alighting_s_per_passenger * alighted_count
            )
            # Evaluate the bounded load term first to avoid unnecessary overflow.
            penalty = self.crowding_strength * load_ratio**self.crowding_exponent
            dwell_s = float(self.base_dwell_s + service_s + service_s * penalty)
        except OverflowError as exc:
            raise ValueError("Computed dwell must be finite") from exc
        if not math.isfinite(dwell_s):
            raise ValueError("Computed dwell must be finite")
        return dwell_s

    def _load_ratio(
        self,
        onboard_load: int | None,
        capacity: int | None,
        boarded_count: int,
        alighted_count: int,
    ) -> float:
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
        if boarded_count > onboard_load:
            raise ValueError("boarded_count must not exceed final onboard_load")
        arrival_load = onboard_load - boarded_count + alighted_count
        if arrival_load > capacity:
            raise ValueError("Passenger counts imply an arrival load above capacity")
        return max(arrival_load, onboard_load) / capacity
