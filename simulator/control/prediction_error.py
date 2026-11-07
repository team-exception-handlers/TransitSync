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
        trains = tuple(self._train(train, truth.time_s) for train in truth.trains)
        transfers = tuple(self._transfer(group) for group in truth.incoming_transfers)
        return replace(truth, trains=trains, incoming_transfers=transfers)

    def _train(self, train: TrainState, now_s: float) -> TrainState:
        load = self._count(train.onboard_load, self.settings.load_kappa)
        if train.predicted_arrival_s is None:
            return replace(train, onboard_load=load)
        sigma = arrival_sigma_s(train.predicted_arrival_s - now_s)
        error_s = sigma * float(self._stream.standard_normal())
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
