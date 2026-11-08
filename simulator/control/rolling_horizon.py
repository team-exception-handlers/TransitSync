# AI contribution: 50% or more AI-generated
"""Bounded coordinated hold search (US-2.6 #61, Mathematical Foundations §8).

Uses the existing candidate grid and break-even objective at every station in
the inclusive forward window. Future choices are provisional: only the current
visit may produce a HoldAction. No schedule or simulator state is retained.
Task #62 subtracts downstream costs from the joint local objective.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from simulator.control.bounded_search import plan_rank, search_grid
from simulator.control.break_even import BreakEvenWeights, evaluate_hold
from simulator.control.downstream import evaluate_downstream, project_visits
from simulator.control.expected_arrivals import TransferEstimate, total_expected_caught
from simulator.control.hold_search import HoldSearchSettings
from simulator.control.interface import ObservationSnapshot
from simulator.control.planning import FutureVisit, RollingHorizonSettings
from simulator.control.walking_cdf import WalkingCdf


@dataclass(frozen=True, slots=True)
class PlannedDecision:
    """A provisional visit and hold duration in simulation seconds."""

    visit: FutureVisit
    hold_s: float


@dataclass(frozen=True, slots=True)
class HorizonAlternative:
    """Best evaluated completion for one hold; ``exact`` labels its search."""

    hold_s: float
    local_net_ps: float
    downstream_cost_ps: float
    net_ps: float
    exact: bool = True


@dataclass(frozen=True, slots=True)
class HorizonPlan:
    """Best evaluated plan, objective, work count and explicit search status."""

    decisions: tuple[PlannedDecision, ...]
    net_ps: float
    combinations_evaluated: int
    local_net_ps: float = 0.0
    downstream_cost_ps: float = 0.0
    alternatives: tuple[HorizonAlternative, ...] = ()
    exact: bool = True
    total_combinations: int = 0

    @property
    def hold_s(self) -> float:
        """Only the first duration may be applied before replanning."""
        return self.decisions[0].hold_s


@dataclass(frozen=True, slots=True)
class RollingHorizonPlanner:
    """Search full hold grids exactly when small, approximately when larger.

    Walking distributions must be supplied from the run's transfer routes,
    keyed by connecting platform. No default walk or headway is invented.
    Unknown transfer platforms contribute no estimated connection benefit.
    """

    walking_by_platform: Mapping[str, WalkingCdf]
    settings: RollingHorizonSettings = field(default_factory=RollingHorizonSettings)
    hold_search: HoldSearchSettings = field(default_factory=HoldSearchSettings)
    weights: BreakEvenWeights = field(default_factory=BreakEvenWeights)

    def __post_init__(self) -> None:
        if not isinstance(self.walking_by_platform, Mapping):
            raise ValueError("walking_by_platform must be a mapping of platform to CDF")
        copied = dict(self.walking_by_platform)
        for platform, walking in copied.items():
            if (
                not isinstance(platform, str)
                or not platform.strip()
                or not callable(getattr(walking, "cdf", None))
            ):
                raise ValueError("walking_by_platform must map non-empty IDs to CDFs")
        object.__setattr__(self, "walking_by_platform", MappingProxyType(copied))

    def plan(self, observation: ObservationSnapshot) -> HorizonPlan:
        """Recompute all choices from this snapshot; never cache future actions.

        Raises ValueError for a missing current visit or a budget too small
        to explore every station. Equal scores prefer less total holding,
        then lexicographically shorter holds (current decision first).
        """
        end_s = observation.time_s + self.settings.window_s
        baseline = project_visits(observation, {}, end_s)
        forecast = _forecast_observation(observation, baseline)
        points = self._points(forecast)
        headways = {p.key: self._headway(p, forecast) for p in points}
        choices = self._choices(points)

        def evaluate(holds):
            decisions = tuple(
                PlannedDecision(p, h) for p, h in zip(points, holds, strict=True)
            )
            return self._evaluate_plan(
                decisions, observation, headways, baseline, end_s, 0
            )

        states, count, exact, total = search_grid(
            choices, self.settings.max_combinations, evaluate
        )
        _, best = max(states.values(), key=lambda pair: plan_rank(*pair))
        return replace(
            best,
            combinations_evaluated=count,
            exact=exact,
            total_combinations=total,
            alternatives=tuple(
                HorizonAlternative(
                    h, r.local_net_ps, r.downstream_cost_ps, r.net_ps, exact
                )
                for h, (_, r) in sorted(states.items())
            ),
        )

    def _choices(self, points):
        """Build complete station grids; the bounded search controls work.

        Every station gets the full grid: even a hold with no local transfer
        benefit can shift a later connection window. Pruning it would miss
        coordinated optima when that later station reaches its own hold cap.
        """
        grid = self.hold_search.candidates()
        return (grid,) * len(points)

    def _evaluate_plan(self, decisions, observation, headways, baseline, end_s, count):
        """Value local holds at projected decision times, then subtract knock-on cost.

        A future point pushed outside the window contributes no hold. Its
        train's existing delay still participates in downstream propagation.
        """
        projected = project_visits(
            observation, {d.visit.key: d.hold_s for d in decisions}, end_s
        )
        by_key = {p.visit.key: p for p in projected}
        # Earlier holds can move a later decision's connection window. Reusing
        # that point's original clock would value the wrong part of the pulse.
        shifted = tuple(
            PlannedDecision(
                replace(d.visit, departure_s=by_key[d.visit.key].due_s),
                by_key[d.visit.key].hold_s,
            )
            for d in decisions
        )
        local = self._net(shifted, observation, headways)
        downstream = evaluate_downstream(
            baseline, projected, observation, self.weights, end_s
        )
        return HorizonPlan(
            decisions, local - downstream.total_ps, count, local, downstream.total_ps
        )

    def _points(self, observation: ObservationSnapshot) -> tuple[FutureVisit, ...]:
        """Put the active decision first, then all remaining window decisions.

        A simultaneous departure belongs to the window too, but the engine's
        current event remains first regardless of its train ID's sort order.
        Repeated platforms are distinguished by trip and stop indices.
        """
        candidates = tuple(
            v
            for v in observation.future_visits
            if v.train_id == observation.train_id
            and v.platform_id == observation.platform_id
            and v.can_hold
        )
        active = tuple(v for v in candidates if v.arrived)
        # Older callers can supply one unambiguous candidate without a marker.
        # Repeated platforms require the observed arrival, never tuple order.
        identified = active or candidates
        current = identified[0] if len(identified) == 1 else None
        if current is None:
            raise ValueError(
                "rolling horizon requires the deciding train's future visit"
            )
        end_s = observation.time_s + self.settings.window_s
        future = sorted(
            (
                v
                for v in observation.future_visits
                if v.key != current.key
                and v.can_hold
                and observation.time_s <= v.departure_s <= end_s
            ),
            key=lambda v: (v.departure_s, v.key),
        )
        return (current, *future)

    def _net(
        self,
        decisions: tuple[PlannedDecision, ...],
        observation: ObservationSnapshot,
        headways: Mapping[tuple, float],
    ) -> float:
        """Sum local break-even gains, sharing each walking group only once.

        Departure order determines which train catches a passenger. A later
        overlapping hold cannot count the same walking interval again.
        """
        loads = {t.train_id: t.onboard_load for t in observation.trains}
        covered = {}
        net = 0.0
        for decision in sorted(
            decisions, key=lambda d: (d.visit.departure_s + d.hold_s, d.visit.key)
        ):
            visit, hold = decision.visit, decision.hold_s
            walking = self.walking_by_platform.get(visit.platform_id)
            caught = 0.0
            if walking is not None:
                caught = self._caught(visit, hold, walking, observation, covered)
            result = evaluate_hold(
                hold,
                caught,
                headways[visit.key],
                loads.get(visit.train_id, 0),
                self.weights,
            )
            net += result.net_ps
        return net

    @staticmethod
    def _headway(visit: FutureVisit, observation: ObservationSnapshot) -> float:
        """Seconds to the next known service, even beyond the planning window.

        With no later service, saved waiting time is unknown and valued at zero.
        """
        later = [
            v.departure_s
            for v in (*observation.future_visits, *observation.headway_visits)
            if v.platform_id == visit.platform_id
            and v.key != visit.key
            and not v.skips_departure
            and v.departure_s > visit.departure_s
        ]
        return min(later) - visit.departure_s if later else 0.0

    @staticmethod
    def _caught(visit, hold, walking, observation, covered) -> float:
        """Apply #41's CDF difference only to previously uncovered intervals."""
        estimates = []
        for group in observation.incoming_transfers:
            if group.platform_id != visit.platform_id:
                continue
            start = max(visit.departure_s, covered.get(group.group_id, -math.inf))
            end = visit.departure_s + hold
            if end > start:
                estimate = TransferEstimate.from_incoming(group, start)
                # Groups can have different overlap with preceding departures.
                estimates.append(
                    total_expected_caught((estimate,), end - start, walking)
                )
            covered[group.group_id] = max(start, end)
        return sum(estimates)


def _forecast_observation(observation, baseline):
    """Use feasible baseline departures when selecting points and headways.

    Visits beyond the projection retain their published estimate, so a known
    later service can still supply the local headway without extending the
    optimization window or inventing a fallback headway.
    """
    reference = {p.visit.key: p for p in baseline}
    return replace(
        observation,
        future_visits=tuple(
            replace(
                v,
                arrival_s=reference[v.key].arrival_s,
                departure_s=reference[v.key].departure_s,
            )
            if v.key in reference
            else v
            for v in observation.future_visits
        ),
    )
