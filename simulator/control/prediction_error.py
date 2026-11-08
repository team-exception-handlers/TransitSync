# AI contribution: 50% or more AI-generated
"""Prediction error model: what a strategy sees instead of the truth (#39).

Implements US-2.1, Task 2.1.3 and Mathematical Foundations section 7:

    estimate = t_actual + kappa * e,   e ~ Normal(mu(tau), sigma(tau)^2)

tau is the prediction horizon, the seconds until the predicted arrival. The
same form is applied to transfer counts and onboard loads, each with its own
kappa, so the effect of each kind of error can be swept separately.
kappa = 0 is perfect-information mode: errors are still drawn, so the stream
is used the same way, but every estimate equals the true value.
"""

import math
from dataclasses import dataclass, replace

import numpy as np

from simulator.control.interface import (
    IncomingTransfer,
    ObservationSnapshot,
    TrainState,
)
from simulator.control.planning import FutureVisit
from simulator.control.validation import finite_number

# Published: the Caltrans GTFS-RT "reliable accuracy" band (Master Service
# Agreement, Exhibit H, equation from Swiftly), with error bounds of
# -60 ln(tau_min + 1.3) and +60 ln(tau_min + 1.5) seconds. No archive of
# predicted against actual REM arrivals exists, so the band's half-width
# (offset 1.4, the midpoint) is read as one standard deviation, with mu = 0
# because the band is almost symmetric. Metro has no real-time feed, so the
# same curve is assumed for it (section 7).
ARRIVAL_SIGMA_SCALE_S = 60.0
ARRIVAL_SIGMA_OFFSET_MIN = 1.4
# Assumed: no archive records passenger counts, so a count's error has a
# standard deviation of 10% of the true count (section 7)
COUNT_RELATIVE_SIGMA = 0.10


def arrival_sigma_s(horizon_s: float) -> float:
    """sigma(tau) in seconds; grows with the horizon tau, in seconds.

    A horizon below 0 (a train already due) is treated as 0.
    """
    horizon_min = max(horizon_s, 0.0) / 60.0
    return ARRIVAL_SIGMA_SCALE_S * math.log(horizon_min + ARRIVAL_SIGMA_OFFSET_MIN)


@dataclass(frozen=True, slots=True)
class PredictionErrorSettings:
    """Error multipliers (kappa) for arrival times, transfer counts and loads.

    1 is the published or assumed error level, below 1 better prediction than
    today and 0 perfect information. Raises ``ValueError`` for a negative,
    infinite or non-numeric value.
    """

    arrival_kappa: float = 1.0
    transfer_kappa: float = 1.0
    load_kappa: float = 1.0

    def __post_init__(self) -> None:
        for name in ("arrival_kappa", "transfer_kappa", "load_kappa"):
            value = getattr(self, name)
            checked = finite_number(f"PredictionErrorSettings.{name}", value, 0)
            object.__setattr__(self, name, checked)

    @property
    def perfect_information(self) -> bool:
        """True when every kappa is 0: an unachievable upper bound (section 7)."""
        return not (self.arrival_kappa or self.transfer_kappa or self.load_kappa)

    def to_dict(self) -> dict[str, float]:
        """Return the multipliers as saved in a scenario file and the manifest."""
        return {
            "arrival_kappa": self.arrival_kappa,
            "transfer_kappa": self.transfer_kappa,
            "load_kappa": self.load_kappa,
        }


class PredictionErrorModel:
    """Turns a true snapshot into the estimated one a strategy receives.

    ``stream`` must be the ``prediction_errors`` stream, so a strategy that
    decides more often never shifts the walking times or group sizes.
    """

    def __init__(
        self, settings: PredictionErrorSettings, stream: np.random.Generator
    ) -> None:
        self.settings = settings
        self._stream = stream

    def apply(self, truth: ObservationSnapshot) -> ObservationSnapshot:
        """Return ``truth`` with error on arrivals, transfer counts and loads.

        Other fields (delays, waiting counts, walk times) are copied unchanged.
        """
        # Keep draws local to this snapshot; later decisions get fresh errors.
        arrival_z: dict[str, float] = {}
        trains = tuple(
            self._train(train, truth.time_s, arrival_z) for train in truth.trains
        )
        transfers = tuple(self._transfer(group) for group in truth.incoming_transfers)
        if not truth.future_visits:
            return replace(truth, trains=trains, incoming_transfers=transfers)
        visits = self._visits(truth, arrival_z)
        # Use the same bounded forecast in both representations of a next stop.
        next_arrivals = {}
        for visit in visits:
            if not visit.arrived:
                next_arrivals.setdefault(
                    (visit.train_id, visit.platform_id), visit.arrival_s
                )
        trains = tuple(
            replace(
                train,
                predicted_arrival_s=next_arrivals.get(
                    (train.train_id, train.next_platform_id), train.predicted_arrival_s
                ),
            )
            for train in trains
        )
        return replace(
            truth, trains=trains, incoming_transfers=transfers, future_visits=visits
        )

    def _visits(
        self, truth: ObservationSnapshot, arrival_z: dict[str, float]
    ) -> tuple[FutureVisit, ...]:
        """Project correlated forecasts onto each train's chronological route."""
        departures: dict[str, float] = {}
        visits = []
        for visit in truth.future_visits:
            previous_s = departures.get(visit.train_id, truth.time_s)
            estimated = self._visit(visit, truth.time_s, arrival_z, previous_s)
            departures[visit.train_id] = estimated.departure_s
            visits.append(estimated)
        return tuple(visits)

    def _visit(
        self,
        visit: FutureVisit,
        now_s: float,
        arrival_z: dict[str, float],
        previous_s: float,
    ) -> FutureVisit:
        """Forecast future visits through the same horizon error model (#61).

        Shift arrival and departure together to preserve dwell. An arrival
        already observed is known. One draw per train retains correlation as
        sigma grows with the horizon. Bound forecasts by known timing and the
        preceding departure: extreme negative draws can otherwise invert stops.
        """
        if visit.arrived or visit.arrival_s <= now_s:
            return visit
        if visit.train_id not in arrival_z:
            arrival_z[visit.train_id] = float(self._stream.standard_normal())
        sigma = arrival_sigma_s(visit.arrival_s - now_s)
        error = self.settings.arrival_kappa * sigma * arrival_z[visit.train_id]
        arrival = visit.arrival_s + error
        if self.settings.arrival_kappa:
            arrival = max(arrival, now_s, previous_s, visit.earliest_arrival_s)
        shift = arrival - visit.arrival_s
        return replace(
            visit,
            arrival_s=arrival,
            departure_s=visit.departure_s + shift,
        )

    def _train(
        self, train: TrainState, now_s: float, arrival_z: dict[str, float]
    ) -> TrainState:
        load = self._count(train.onboard_load, self.settings.load_kappa)
        if train.predicted_arrival_s is None:
            return replace(train, onboard_load=load)
        sigma = arrival_sigma_s(train.predicted_arrival_s - now_s)
        z = float(self._stream.standard_normal())
        arrival_z[train.train_id] = z
        error_s = sigma * z
        arrival_s = train.predicted_arrival_s + self.settings.arrival_kappa * error_s
        return replace(train, predicted_arrival_s=arrival_s, onboard_load=load)

    def _transfer(self, group: IncomingTransfer) -> IncomingTransfer:
        # One draw scales both counts, so still walking <= group size holds
        z = float(self._stream.standard_normal())
        kappa = self.settings.transfer_kappa
        return replace(
            group,
            passenger_count=_scaled(group.passenger_count, kappa, z),
            group_size=_scaled(group.group_size, kappa, z),
        )

    def _count(self, value: int, kappa: float) -> int:
        return _scaled(value, kappa, float(self._stream.standard_normal()))


def _scaled(value: int, kappa: float, z: float) -> int:
    """A count with relative error ``kappa * 10% * z``, rounded, never below 0."""
    return max(0, round(value * (1.0 + kappa * COUNT_RELATIVE_SIGMA * z)))
