# AI contribution: 50% or more AI-generated
"""Forward movement and marginal downstream costs (US-2.6 #62).

Mathematical Foundations §§1,6,8: compare each candidate with an otherwise
identical zero-hold forecast. Timetable order, platform occupancy, arrival and
departure separation, dispatch suspensions and terminal recovery match the
train engine. Predictions never mutate trains or schedule actual events.
"""

import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter

from simulator.control.break_even import BreakEvenWeights
from simulator.control.interface import ObservationSnapshot
from simulator.control.planning import FutureVisit, VisitKey
from simulator.control.validation import finite_number
from simulator.trains.suspension import dispatch_ready_s


@dataclass(frozen=True, slots=True)
class ProjectedVisit:
    """One visit's arrival, decision readiness and actual departure, in seconds."""

    visit: FutureVisit
    arrival_s: float
    due_s: float
    departure_s: float
    hold_s: float


def _predecessors(visits, identity, ordering):
    """Find preceding visits per train or platform in a stable timetable order."""
    groups = defaultdict(list)
    for visit in visits:
        groups[identity(visit)].append(visit)
    previous = {}
    for group in groups.values():
        ordered = sorted(group, key=ordering)
        previous.update(
            (current.key, prior.key)
            for prior, current in zip(ordered, ordered[1:], strict=False)
        )
    return previous


def _visit_order(visits):
    """Order the immutable route/platform dependencies before predicting times.

    Occupied platforms lead not-yet-arrived services, even if a delayed return
    trip originally had an earlier timetable slot. A dependency cycle is an
    inconsistent forecast; fail clearly instead of manufacturing departures.
    """
    by_key = {v.key: v for v in visits}
    if len(by_key) != len(visits):
        raise ValueError("future visit keys must be unique")
    trains = _predecessors(visits, lambda v: v.train_id, lambda v: v.key[1:])
    platforms = _predecessors(
        visits,
        lambda v: v.platform_id,
        lambda v: (not v.arrived, v.scheduled_arrival_s, v.key),
    )
    graph = {
        v.key: tuple(
            k for k in (trains.get(v.key), platforms.get(v.key)) if k is not None
        )
        for v in visits
    }
    try:
        order = tuple(TopologicalSorter(graph).static_order())
    except CycleError as error:
        raise ValueError("future train and platform orders conflict") from error
    return by_key, trains, platforms, order


def project_visits(
    observation: ObservationSnapshot, holds: Mapping[VisitKey, float], end_s: float
) -> tuple[ProjectedVisit, ...]:
    """Project remaining visits whose unheld arrival is within ``end_s``.

    A delayed visit remains in the forecast even if pushed beyond the window.
    Future holds start only if their projected decision is within the window.
    Raise ValueError for contradictory train/platform order or duplicate visits.
    """
    end_s = finite_number("projection end_s", end_s, observation.time_s)
    holds = {
        key: finite_number("projected hold_s", seconds, 0)
        for key, seconds in holds.items()
    }
    visits = tuple(
        v for v in observation.future_visits if v.arrival_s <= end_s or v.arrived
    )
    by_key, trains, platforms, order = _visit_order(visits)
    projected = {}
    last_departures = {p.platform_id: p.last_departure_s for p in observation.platforms}
    lines = {t.train_id: t.line_id for t in observation.trains}
    for key in order:
        visit = by_key[key]
        prior_train = projected.get(trains.get(key))
        prior_platform = projected.get(platforms.get(key))
        arrival = _arrival(visit, prior_train, prior_platform, observation)
        due = max(observation.time_s, arrival + visit.departure_s - visit.arrival_s)
        hold = holds.get(key, 0.0) if visit.can_hold and due <= end_s else 0.0
        departure = _departure(
            visit, due + hold, prior_platform, last_departures, lines, observation
        )
        if visit.skips_departure:
            due = departure = arrival
        projected[key] = ProjectedVisit(visit, arrival, due, departure, hold)
    return tuple(projected[v.key] for v in visits)


def _arrival(visit, prior_train, prior_platform, observation):
    """Propagate route delay, then apply platform separation and occupancy."""
    if visit.arrived:
        return visit.arrival_s
    arrival = max(observation.time_s, visit.arrival_s, visit.earliest_arrival_s)
    if prior_train is not None:
        previous = prior_train.visit
        if previous.trip_index != visit.trip_index:
            extra = max(
                0.0, prior_train.arrival_s - previous.arrival_s - visit.recovery_s
            )
            arrival = max(arrival, visit.arrival_s + extra)
        else:
            travel = visit.scheduled_arrival_s - previous.scheduled_departure_s
            arrival = max(arrival, prior_train.departure_s + max(0.0, travel))
    if prior_platform is not None:
        arrival = max(arrival, prior_platform.arrival_s + observation.minimum_gap_s)
        if not prior_platform.visit.skips_departure:
            arrival = max(arrival, math.nextafter(prior_platform.departure_s, math.inf))
    return arrival


def _departure(visit, ready, prior_platform, last_departures, lines, observation):
    """Use the engine's half-open dispatch intervals and departure-gap rule."""
    if visit.stop_index == 0:
        ready = dispatch_ready_s(
            lines.get(visit.train_id, ""), ready, observation.suspensions
        )
    previous = last_departures.get(visit.platform_id)
    if prior_platform is not None and not prior_platform.visit.skips_departure:
        previous = prior_platform.departure_s
    if previous is not None:
        ready = max(ready, previous + observation.minimum_gap_s)
    return ready


@dataclass(frozen=True, slots=True)
class DownstreamCost:
    """Extra onboard and platform waiting costs, both in passenger-seconds."""

    onboard_ps: float = 0.0
    waiting_ps: float = 0.0

    @property
    def total_ps(self) -> float:
        """The downstream term accepted by the existing break-even function."""
        return self.onboard_ps + self.waiting_ps


def evaluate_downstream(
    baseline: tuple[ProjectedVisit, ...],
    candidate: tuple[ProjectedVisit, ...],
    observation: ObservationSnapshot,
    weights: BreakEvenWeights,
    end_s: float,
) -> DownstreamCost:
    """Charge only new delay relative to the zero-hold forecast.

    Onboard delay is charged when first incurred, not again at every station;
    explicit holds are already charged by the local objective. Current platform
    queues wait for their first remaining departure and are charged once there.
    No unavailable future loads, passengers or cost weights are invented.
    Onboard counts stay at their observed estimates throughout the forecast.
    Thus these are marginal costs for known riders, not a demand simulation.
    The explicit local L*h cost is subtracted before charging extra delay,
    including when a dispatch closure adds more time than the proposed hold.
    """
    reference = {p.visit.key: p for p in baseline}
    proposed = {p.visit.key: p for p in candidate}
    loads = {t.train_id: t.onboard_load for t in observation.trains}
    prior_delays = {}
    onboard_ps = 0.0
    for projected in sorted(candidate, key=lambda p: p.visit.key):
        visit = projected.visit
        base = reference.get(visit.key)
        if base is None:
            continue
        added = _added_delay(base, projected, end_s)
        # Carrying a ten-second delay through three stops is still ten seconds
        # for the same riders. Recovery can remove the carried part once.
        carried = max(0.0, prior_delays.get(visit.train_id, 0.0) - visit.recovery_s)
        extra = max(0.0, added - carried - projected.hold_s)
        onboard_ps += loads.get(visit.train_id, 0) * extra * weights.w_onboard
        prior_delays[visit.train_id] = added
    waiting_ps = _waiting_cost(baseline, proposed, observation, weights, end_s)
    return DownstreamCost(onboard_ps, waiting_ps)


def _added_delay(base, projected, end_s):
    """Clip both forecasts to the same window before taking their difference."""
    return max(0.0, min(end_s, projected.departure_s) - min(end_s, base.departure_s))


def _waiting_cost(baseline, proposed, observation, weights, end_s):
    """Charge each observed queue at its first service with available capacity.

    Full vehicles cannot serve the queue; future boarding and alighting are
    unknown, so use the supplied load/capacity estimates without inventing them.
    """
    waiting = {p.platform_id: p.waiting_count for p in observation.platforms}
    full = {t.train_id for t in observation.trains if t.onboard_load >= t.capacity}
    charged_platforms = set()
    waiting_ps = 0.0
    # Platform ordering is separate from route ordering: only the first service
    # can carry passengers already waiting at this snapshot's platform.
    for base in sorted(baseline, key=lambda p: (p.departure_s, p.visit.key)):
        visit = base.visit
        if (
            visit.skips_departure
            or visit.platform_id in charged_platforms
            or visit.train_id in full
        ):
            continue
        projected = proposed.get(visit.key)
        if projected is None:
            continue
        delay = _added_delay(base, projected, end_s)
        waiting_ps += waiting.get(visit.platform_id, 0) * delay * weights.w_wait
        charged_platforms.add(visit.platform_id)
    return waiting_ps
