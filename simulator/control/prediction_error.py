# AI contribution: 50% or more AI-generated
"""Prediction error model: what a strategy sees instead of the truth (#39).

Implements US-2.1, Task 2.1.3 and Mathematical Foundations section 7:

    estimate = t_actual + kappa * e,   e ~ Normal(mu(tau), sigma(tau)^2)

tau is the prediction horizon, the seconds until the predicted arrival. The
same form is applied to transfer counts and onboard loads, each with its own
kappa, so the effect of each kind of error can be swept separately.
kappa = 0 is perfect-information mode: errors are still drawn, but every
estimate equals the true value.

Each e is keyed by what it predicts (the decision, the value type and the
train or group), not by draw order, so paired runs with the same seed give the
same prediction the same e even when a hold changes the other snapshots
(section 9, #192).
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import partial

from simulator.control.interface import (
    IncomingTransfer,
    ObservationSnapshot,
    TrainState,
)
from simulator.control.planning import FutureVisit
from simulator.control.validation import finite_number
from simulator.engine.random_streams import StreamManager

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


def _updated[Record](record: Record, **changes: object) -> Record:
    """Copy a frozen dataclass with ``changes``, keeping its own type.

    ``dataclasses.replace`` is typed as returning a generic dataclass, so
    static checkers lose the concrete type (``TrainState``, ``FutureVisit``,
    ...). This wrapper restores it for every copy made in this module.
    """
    return replace(record, **changes)


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

    ``draw(*key)`` returns the standard normal e for ``key``; in a run it is
    ``StreamManager.keyed_normal`` on the ``prediction_errors`` stream, so a
    strategy that decides more often never shifts the walking times or group
    sizes.
    """

    def __init__(
        self, settings: PredictionErrorSettings, draw: Callable[..., float]
    ) -> None:
        self.settings = settings
        self._draw = draw

    def apply(self, truth: ObservationSnapshot) -> ObservationSnapshot:
        """Return ``truth`` with error on arrivals, transfer counts and loads.

        Other fields (delays, waiting counts, walk times) are copied unchanged.
        """
        # A hold delays a departure but never changes its scheduled time, so
        # this names the same decision in both runs of a pair
        decision = (truth.train_id, truth.platform_id, truth.scheduled_departure_s)
        arrival_z: dict[str, float] = {}
        draw = _decision_draw(self._draw, decision)
        trains = self._trains(truth.trains, truth.time_s, draw, arrival_z)
        transfers = tuple(
            self._transfer(group, draw) for group in truth.incoming_transfers
        )
        if not truth.future_visits and not truth.headway_visits:
            return _updated(truth, trains=trains, incoming_transfers=transfers)
        departures: dict[str, float] = {}
        visits = self._visits(
            truth.future_visits, truth.time_s, draw, arrival_z, departures
        )
        headways = self._visits(
            truth.headway_visits, truth.time_s, draw, arrival_z, departures
        )
        # Use the same bounded forecast in both representations of a next stop.
        next_arrivals = {}
        for visit in (*visits, *headways):
            if not visit.arrived:
                next_arrivals.setdefault(
                    (visit.train_id, visit.platform_id), visit.arrival_s
                )
        trains = tuple(
            _copy_train(
                train,
                next_arrivals.get(
                    (train.train_id, train.next_platform_id), train.predicted_arrival_s
                ),
                train.onboard_load,
            )
            for train in trains
        )
        return _updated(
            truth,
            trains=trains,
            incoming_transfers=transfers,
            future_visits=visits,
            headway_visits=headways,
        )

    def _visits(
        self,
        source: tuple[FutureVisit, ...],
        now_s: float,
        draw: Callable[..., float],
        arrival_z: dict[str, float],
        departures: dict[str, float],
    ) -> tuple[FutureVisit, ...]:
        """Project correlated forecasts onto each train's chronological route."""
        visits = []
        for visit in source:
            previous_s = departures.get(visit.train_id, now_s)
            estimated = self._visit(visit, now_s, draw, arrival_z, previous_s)
            departures[visit.train_id] = estimated.departure_s
            visits.append(estimated)
        return tuple(visits)

    def _visit(
        self,
        visit: FutureVisit,
        now_s: float,
        draw: Callable[..., float],
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
            arrival_z[visit.train_id] = draw("arrival", visit.train_id)
        sigma = arrival_sigma_s(visit.arrival_s - now_s)
        error = self.settings.arrival_kappa * sigma * arrival_z[visit.train_id]
        arrival = visit.arrival_s + error
        if self.settings.arrival_kappa:
            arrival = max(arrival, now_s, previous_s, visit.earliest_arrival_s)
        shift = arrival - visit.arrival_s
        return _copy_visit(visit, arrival, visit.departure_s + shift)

    def _trains(
        self,
        trains: tuple[TrainState, ...],
        now_s: float,
        draw: Callable[..., float],
        arrival_z: dict[str, float],
    ) -> tuple[TrainState, ...]:
        """Estimate each train with this decision's bound keyed draw."""
        return tuple(self._train(t, now_s, draw, arrival_z) for t in trains)

    def _train(
        self,
        train: TrainState,
        now_s: float,
        draw: Callable[..., float],
        arrival_z: dict[str, float],
    ) -> TrainState:
        z_load = draw("load", train.train_id)
        load = _scaled(train.onboard_load, self.settings.load_kappa, z_load)
        arrival_s = train.predicted_arrival_s
        if arrival_s is not None:
            sigma = arrival_sigma_s(arrival_s - now_s)
            z = draw("arrival", train.train_id)
            arrival_z[train.train_id] = z
            error_s = sigma * z
            arrival_s = arrival_s + self.settings.arrival_kappa * error_s
        return _copy_train(train, arrival_s, load)

    def _transfer(
        self, group: IncomingTransfer, draw: Callable[..., float]
    ) -> IncomingTransfer:
        # One draw scales both counts, so still walking <= group size holds
        z = draw("transfer", group.group_id)
        kappa = self.settings.transfer_kappa
        return _updated(
            group,
            passenger_count=_scaled(group.passenger_count, kappa, z),
            group_size=_scaled(group.group_size, kappa, z),
        )


def _scaled(value: int, kappa: float, z: float) -> int:
    """A count with relative error ``kappa * 10% * z``, rounded, never below 0."""
    return max(0, round(value * (1.0 + kappa * COUNT_RELATIVE_SIGMA * z)))


def _decision_draw(draw: Callable[..., float], decision: tuple) -> Callable[..., float]:
    """Return ``draw`` with this decision's key fixed in front of every call.

    The run passes ``partial(streams.keyed_normal, name)``. For exactly that
    form the stream manager hashes the shared key start once per decision
    (#412), and the numbers are identical. Any other callable is wrapped as is.
    """
    func = getattr(draw, "func", None)
    if (
        type(draw) is partial
        and not draw.keywords
        and getattr(func, "__func__", None) is StreamManager.keyed_normal
    ):
        return func.__self__.keyed_normal_from(*draw.args, *decision)
    return partial(draw, *decision)


def _copy_train(train: TrainState, arrival_s: float | None, load: int) -> TrainState:
    """Copy the fixed train schema without rediscovering dataclass fields.

    Fields are passed by position, so test_prediction_copy pins the field
    order. Full-day observations create millions of these values. Keep subclass
    handling on dataclasses.replace so extensions retain their concrete type
    and extra fields. Random draws and arithmetic remain in the caller.
    """
    if (
        load == train.onboard_load
        and type(load) is type(train.onboard_load)
        and _same_number(arrival_s, train.predicted_arrival_s)
    ):
        return train
    if type(train) is not TrainState:
        return _updated(train, predicted_arrival_s=arrival_s, onboard_load=load)
    return TrainState(
        train.train_id,
        train.line_id,
        train.next_platform_id,
        arrival_s,
        train.scheduled_departure_s,
        train.delay_s,
        load,
        train.capacity,
    )


def _same_number(first: float | None, second: float | None) -> bool:
    """Reuse frozen values only when type and signed-zero representation match."""
    return first is second or (
        type(first) is type(second)
        and first == second
        and (first != 0 or math.copysign(1, first) == math.copysign(1, second))
    )


def _copy_visit(
    visit: FutureVisit, arrival_s: float, departure_s: float
) -> FutureVisit:
    """Copy a fixed forecast schema, preserving subclass extension fields.

    Positional like ``_copy_train``; its field order is pinned by a test too.
    """
    if type(visit) is not FutureVisit:
        return _updated(visit, arrival_s=arrival_s, departure_s=departure_s)
    return FutureVisit(
        visit.train_id,
        visit.trip_index,
        visit.stop_index,
        visit.station_id,
        visit.platform_id,
        arrival_s,
        departure_s,
        visit.scheduled_arrival_s,
        visit.scheduled_departure_s,
        visit.can_hold,
        visit.skips_departure,
        visit.recovery_s,
        visit.arrived,
        visit.earliest_arrival_s,
    )
