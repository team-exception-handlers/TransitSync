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
from functools import lru_cache
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
    return prepare_projection(observation, end_s)(holds)


def prepare_projection(
    observation: ObservationSnapshot, end_s: float, *, validated_holds=False
):
    """Prepare one immutable forecast's dependency order for repeated holds.

    The graph, line IDs and departure history cannot change between candidates
    of one decision. Keep them local to this call, never across observations.
    Per-visit memoization reuses identical parent arrival/departure boundaries;
    no hold combination, constraint, or objective calculation is skipped.
    Each key includes the proposed hold and both parents' timing boundaries.
    Recovery, occupancy and skipped-departure flags remain fixed visit inputs.
    """
    end_s = finite_number("projection end_s", end_s, observation.time_s)
    visits = tuple(
        v for v in observation.future_visits if v.arrival_s <= end_s or v.arrived
    )
    by_key, trains, platforms, order = _visit_order(visits)
    keys = tuple(v.key for v in visits)
    last_departures = {p.platform_id: p.last_departure_s for p in observation.platforms}
    lines = {t.train_id: t.line_id for t in observation.trains}
    memo = {key: {} for key in order}

    def project(holds):
        # Only the planner may supply its already validated HoldSearch grid.
        # Public project_visits still validates all external hold values.
        if not validated_holds:
            holds = {
                key: finite_number("projected hold_s", seconds, 0)
                for key, seconds in holds.items()
            }
        projected = {}
        for key in order:
            prior_train = projected.get(trains.get(key))
            prior_platform = projected.get(platforms.get(key))
            boundary = (
                holds.get(key, 0.0),
                _boundary(prior_train),
                _boundary(prior_platform),
            )
            if boundary not in memo[key]:
                memo[key][boundary] = _project_visit(
                    by_key[key],
                    prior_train,
                    prior_platform,
                    observation,
                    end_s,
                    holds.get(key, 0.0),
                    last_departures,
                    lines,
                )
            projected[key] = memo[key][boundary]
        return tuple(projected[key] for key in keys)

    return project


def _boundary(prior):
    """Only a parent's arrival/departure times affect this fixed child visit."""
    return None if prior is None else (prior.arrival_s, prior.departure_s)


def _project_visit(
    visit,
    prior_train,
    prior_platform,
    observation,
    end_s,
    requested,
    last_departures,
    lines,
):
    """Apply the unchanged movement rules once for a unique parent boundary."""
    arrival = _arrival(visit, prior_train, prior_platform, observation)
    due = max(observation.time_s, arrival + visit.departure_s - visit.arrival_s)
    hold = requested if visit.can_hold and due <= end_s else 0.0
    departure = _departure(
        visit, due + hold, prior_platform, last_departures, lines, observation
    )
    if visit.skips_departure:
        due = departure = arrival
    return ProjectedVisit(visit, arrival, due, departure, hold)


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


def prepare_downstream(baseline, observation, weights, end_s, *, ordered=False):
    """Prepare invariant cost inputs once for one decision's candidate search.

    Cache each train's marginal contributions independently: its carried delay
    depends only on its own projected departures, holds and fixed recovery.
    Summation still follows the original visit order, without regrouping sums
    that could change floating-point scores or tie-breaking. The planner's
    ordered projection permits fixed tuple positions; external candidates
    retain key lookup and support incomplete or reordered lists.
    """
    by_train = defaultdict(list)
    positions = {p.visit.key: i for i, p in enumerate(baseline)}
    for base in sorted(baseline, key=lambda p: p.visit.key):
        by_train[base.visit.train_id].append(base)
    loads = {t.train_id: t.onboard_load for t in observation.trains}
    full = {t.train_id for t in observation.trains if t.onboard_load >= t.capacity}
    waiting = {p.platform_id: p.waiting_count for p in observation.platforms}
    served = set()
    services = []
    for base in sorted(baseline, key=lambda p: (p.departure_s, p.visit.key)):
        visit = base.visit
        if (
            visit.skips_departure
            or visit.arrived
            or visit.train_id in full
            or visit.platform_id in served
        ):
            continue
        services.append(base)
        served.add(visit.platform_id)

    @lru_cache(maxsize=8192)
    def train_costs(train_id, timings):
        return _train_costs(
            by_train[train_id], timings, loads.get(train_id, 0), weights, end_s
        )

    train_positions = tuple(
        (train_id, tuple(positions[p.visit.key] for p in visits))
        for train_id, visits in by_train.items()
    )
    service_positions = tuple((base, positions[base.visit.key]) for base in services)

    def evaluate(candidate):
        if not ordered:
            proposed = {p.visit.key: p for p in candidate}
            if any(base.visit.key not in proposed for base in baseline):
                # Public callers may omit visits or supply a different order.
                return evaluate_downstream(
                    baseline, candidate, observation, weights, end_s
                )
            candidate = tuple(proposed[base.visit.key] for base in baseline)
        onboard_ps = 0.0
        for train_id, indices in train_positions:
            timings = tuple(
                (candidate[i].departure_s, candidate[i].hold_s) for i in indices
            )
            for contribution in train_costs(train_id, timings):
                onboard_ps += contribution
        waiting_ps = 0.0
        for base, index in service_positions:
            projected = candidate[index]
            delay = _added_delay(base, projected, end_s)
            waiting_ps += (
                waiting.get(base.visit.platform_id, 0) * delay * weights.w_wait
            )
        return DownstreamCost(onboard_ps, waiting_ps)

    return evaluate


def _train_costs(visits, timings, load, weights, end_s):
    """Keep per-visit arithmetic and recovery order identical to the baseline."""
    costs = []
    prior = 0.0
    for base, (departure_s, hold_s) in zip(visits, timings, strict=True):
        added = max(0.0, min(end_s, departure_s) - min(end_s, base.departure_s))
        carried = max(0.0, prior - base.visit.recovery_s)
        extra = max(0.0, added - carried - hold_s)
        costs.append(load * extra * weights.w_onboard)
        prior = added
    return tuple(costs)


def _added_delay(base, projected, end_s):
    """Clip both forecasts to the same window before taking their difference."""
    return max(0.0, min(end_s, projected.departure_s) - min(end_s, base.departure_s))


def _waiting_cost(baseline, proposed, observation, weights, end_s):
    """Charge each observed queue at its first service with available capacity.

    Full vehicles cannot serve the queue; future boarding and alighting are
    unknown, so use the supplied load/capacity estimates without inventing them.
    Arrived trains have already boarded everyone they can take. Any observed
    residual queue needs a later service, even if that train still has seats
    but has exhausted its door budget or cannot serve those destinations.
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
            or visit.arrived
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
