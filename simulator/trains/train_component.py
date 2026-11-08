# AI contribution: 50% or more AI-generated
"""Connect trains, passenger queues and disruptions to the event engine.

US-1.2 movement and US-1.3 #100 passenger transitions share one platform clock.
Arrival opens doors; the actual departure closes them after any hold, dispatch
suspension or minimum-gap wait. Passenger rules are delegated to PlatformQueue.
Only this component mutates vehicle loads through that queue, avoiding duplicate
boarding owners. Controllers receive copied states rather than live queues.
Passengers keep their IDs across transfers, boarding and destination alighting.
External feeder entries contribute movement counts without changing the load
of passengers already represented by an aggregate train count.

This file exceeds 500 lines because arrival, hold and departure handlers share
trip cursors and platform occupancy. Keeping those state transitions together
preserves one train-state owner; passenger journey rules live in their own module.
All event times, dwell durations and separation gaps are simulation seconds.
"""

import math
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any

from simulator.control.decision import DecisionPipeline
from simulator.control.interface import PlatformState, TrainState
from simulator.control.planning import FutureVisit
from simulator.engine.event_queue import Scheduler
from simulator.engine.events import (
    Alighting,
    Boarding,
    DepartureClearance,
    DepartureDue,
    Event,
    Hold,
    HoldEnd,
    PassengerArrival,
    TrainArrival,
    TrainDeparture,
)
from simulator.passengers.platform_queue import PlatformQueue
from simulator.trains.disruption import DelayInjection
from simulator.trains.door_throughput import DoorThroughput
from simulator.trains.suspension import LineSuspension, dispatch_ready_s
from simulator.trains.train import ScheduledStop, Train

Visit = tuple[str, int, int]


class TrainComponent:
    """Own train movement, platform separation and optional passenger queues."""

    def __init__(
        self,
        trains: Sequence[Train],
        minimum_gap_s: float = 90.0,
        *,
        suspensions: Sequence[LineSuspension] = (),
        delay_injections: Sequence[DelayInjection] = (),
        passenger_queue: PlatformQueue | None = None,
        decision: DecisionPipeline | None = None,
        rem_door_throughput: Mapping[str, DoorThroughput] | None = None,
    ) -> None:
        """Bind fresh vehicles, a passenger queue and a departure decision policy.

        Trains retain identity across return trips. Minimum gap is positive
        seconds; suspensions and delay injections use the same simulation clock.
        A queue with passenger snapshots also validates initial onboard manifests.
        Queue-owned identities share the same vehicle capacity as aggregate load.
        rem_door_throughput explicitly identifies REM train IDs and their door
        rates. Unlisted vehicles retain capacity-only boarding; no line inference.
        Raises ValueError for invalid configuration, duplicate train identities
        or inconsistent passenger manifests before any event is scheduled.
        """
        if (
            isinstance(minimum_gap_s, bool)
            or not isinstance(minimum_gap_s, int | float)
            or not math.isfinite(minimum_gap_s)
            or minimum_gap_s <= 0
        ):
            raise ValueError("Minimum gap must be finite and positive")
        self.minimum_gap_s = float(minimum_gap_s)
        self.trains: dict[str, Train] = {}
        self._schedules: dict[str, tuple[tuple[ScheduledStop, ...], ...]] = {}
        self._visits: dict[str, list[Visit]] = defaultdict(list)
        self.suspensions = tuple(suspensions)
        if any(not isinstance(item, LineSuspension) for item in self.suspensions):
            raise ValueError("Suspensions must be LineSuspension instances")
        self.delay_injections = tuple(delay_injections)
        if any(not isinstance(item, DelayInjection) for item in self.delay_injections):
            raise ValueError("Delay injections must be DelayInjection instances")
        ids = [item.disruption_id for item in self.delay_injections]
        if len(ids) != len(set(ids)):
            raise ValueError("Delay injection IDs must be unique")
        self._scheduled_disruptions: dict[str, dict[str, float]] = {}
        self._applied_disruptions: set[str] = set()
        self._disruptions_by_arrival: dict[Visit, list[str]] = defaultdict(list)
        self._arrival_wait: dict[Visit, float] = {}
        self._arrival_cursor: dict[str, int] = {}
        self._departure_cursor: dict[str, int] = {}
        self._ready_arrivals: dict[Visit, float] = {}
        self._ready_departures: dict[Visit, float] = {}
        self._arrival_queued: set[Visit] = set()
        self._departure_queued: set[Visit] = set()
        self._clearance_queued: set[Visit] = set()
        self._skipped_departures: set[Visit] = set()
        self._last_arrival: dict[str, float] = {}
        self._last_departure: dict[str, float] = {}
        self._occupied_platforms: dict[str, Visit] = {}
        self._at_platform: dict[str, deque[Visit]] = defaultdict(deque)
        self._boarded: dict[Visit, int] = defaultdict(int)
        self._finished: set[str] = set()
        # Asked at every DepartureDue; no control unless a strategy is given
        self.decision = decision or DecisionPipeline()
        self._hold_s: dict[Visit, float] = {}
        self._unheld_ready_s: dict[Visit, float] = {}

        for train in trains:
            if train.id in self.trains:
                raise ValueError(f"Duplicate train ID: {train.id}")
            self.trains[train.id] = train
            schedules = (train.schedule, *train.return_trips)
            self._schedules[train.id] = schedules
            self._register_trip_visits(train.id, 0)
        if self.suspensions and any(not train.line_id.strip() for train in trains):
            raise ValueError("Trains need explicit line IDs when suspensions are used")

        for platform, visits in self._visits.items():
            visits.sort(key=self._visit_sort_key)
            self._arrival_cursor[platform] = 0
            self._departure_cursor[platform] = 0
        self._bind_rem_throughput(rem_door_throughput)
        self._bind_passengers(passenger_queue)

    def _bind_rem_throughput(
        self, rem_door_throughput: Mapping[str, DoorThroughput] | None
    ) -> None:
        """Validate explicit REM identities before installing passenger manifests."""
        if rem_door_throughput is not None and not isinstance(
            rem_door_throughput, Mapping
        ):
            raise ValueError("rem_door_throughput must map train IDs to DoorThroughput")
        self.rem_door_throughput = MappingProxyType(dict(rem_door_throughput or {}))
        if any(
            key not in self.trains or not isinstance(value, DoorThroughput)
            for key, value in self.rem_door_throughput.items()
        ):
            raise ValueError(
                "rem_door_throughput requires known train IDs and DoorThroughput values"
            )

    def _bind_passengers(self, queue: PlatformQueue | None) -> None:
        """Attach one passenger owner after all train identities are known."""
        if queue is not None and not isinstance(queue, PlatformQueue):
            raise ValueError("passenger_queue must be a PlatformQueue")
        self.passenger_queue = queue
        if queue is not None:
            queue.bind_trains(self.trains)

    def _stop(self, visit: Visit) -> ScheduledStop:
        """Look up a stop by vehicle, trip and stop index.

        The retained schedules remain valid even when Train.schedule switches
        to a return trip. Event handling must not confuse those two visits.
        """
        train_id, trip_index, stop_index = visit
        return self._schedules[train_id][trip_index][stop_index]

    def _visit_sort_key(self, visit: Visit) -> tuple[float, str, int, int]:
        """Order visits by scheduled seconds, then stable identity.

        Equal timetable arrivals must resolve consistently across seeded runs.
        Actual platform availability is enforced later when arrivals are released.
        """
        return (self._stop(visit).arrival_s, visit[0], visit[1], visit[2])

    def _register_trip_visits(self, train_id: str, trip_index: int) -> None:
        """Register only the trip whose preceding turnaround has completed.

        Registering return visits earlier could let an inactive trip block the
        platform ahead of a vehicle that is already ready to arrive.
        """
        for stop_index, stop in enumerate(self._schedules[train_id][trip_index]):
            self._visits[stop.platform_id].append((train_id, trip_index, stop_index))
            self._arrival_cursor.setdefault(stop.platform_id, 0)
            self._departure_cursor.setdefault(stop.platform_id, 0)

    def _next_visit(self, platform: str, cursors: dict[str, int]) -> Visit | None:
        """Return the next unprocessed visit, or None when service is exhausted.

        Arrival and departure use separate cursors because a dwelling vehicle
        has already arrived but still owns the platform until it departs.
        """
        index = cursors[platform]
        visits = self._visits[platform]
        return visits[index] if index < len(visits) else None

    def _sort_pending_visits(self, platform: str, cursor: dict[str, int]) -> None:
        """Insert activated return trips without reordering completed visits.

        Only the suffix beyond the relevant cursor is mutable; changing the
        prefix would change which vehicle currently owns the platform.
        """
        visits = self._visits[platform]
        index = cursor[platform]
        visits[index:] = sorted(visits[index:], key=self._visit_sort_key)

    def start(self, scheduler: Scheduler) -> None:
        """Schedule the first arrival for each train."""
        for train in self.trains.values():
            first_stop = self._schedules[train.id][0][0]
            self._ready_arrivals[(train.id, 0, 0)] = max(
                0.0, first_stop.arrival_s + train.current_delay
            )
        for platform in sorted(self._visits):
            self._release_arrival(platform, scheduler)

    def _release_arrival(self, platform: str, scheduler: Scheduler) -> None:
        """Schedule the next ready arrival after platform and spacing constraints.

        A reserved or occupied platform cannot accept another vehicle. Delay
        injections apply once to a matching arrival and propagate with the train.
        The departure boundary uses the next float because arrivals sort first.
        """
        visit = self._next_visit(platform, self._arrival_cursor)
        if (
            visit is None
            or visit not in self._ready_arrivals
            or visit in self._arrival_queued
            or platform in self._occupied_platforms
        ):
            return
        train = self.trains[visit[0]]
        stop = self._stop(visit)
        requested_s = self._ready_arrivals[visit]
        safe_s = max(
            requested_s,
            self._last_arrival.get(platform, -math.inf) + self.minimum_gap_s,
        )
        if platform in self._last_departure:
            # Arrivals sort before departures; use the next representable time
            # so a newly vacant platform can accept a train after it departs.
            safe_s = max(
                safe_s, math.nextafter(self._last_departure[platform], math.inf)
            )
        self._arrival_wait[visit] = safe_s - requested_s
        injected_s = 0.0
        for disruption in self.delay_injections:
            if disruption.disruption_id in self._scheduled_disruptions:
                continue
            if disruption.matches(
                train_id=train.id,
                station_id=stop.station_id,
                platform_id=platform,
                arrival_s=safe_s,
            ):
                injected_s += disruption.delay_s
                self._scheduled_disruptions[disruption.disruption_id] = {
                    "trigger_time_s": safe_s,
                    "arrival_time_s": safe_s + injected_s,
                }
                self._disruptions_by_arrival[visit].append(disruption.disruption_id)
        safe_s += injected_s
        scheduler.schedule(
            TrainArrival(
                time_s=safe_s,
                train_id=train.id,
                station_id=stop.station_id,
                platform_id=platform,
                scheduled_s=stop.arrival_s,
                disruption_delay_s=train.disruption_delay_at(
                    safe_s, stop.arrival_s, inherited_wait_s=self._arrival_wait[visit]
                ),
            )
        )
        self._arrival_queued.add(visit)

    def manifest_entries(self) -> tuple[dict[str, object], ...]:
        """Return delay configurations and whether each one actually occurred."""
        entries = []
        for disruption in self.delay_injections:
            configured = self._scheduled_disruptions.get(disruption.disruption_id)
            applied = disruption.disruption_id in self._applied_disruptions
            entries.append(
                {
                    **disruption.to_manifest_record(),
                    "applied": applied,
                    "trigger_time_s": (
                        configured["trigger_time_s"] if applied and configured else None
                    ),
                    "arrival_time_s": (
                        configured["arrival_time_s"] if applied and configured else None
                    ),
                }
            )
        return tuple(entries)

    def boarding_manifest_entries(self) -> tuple[dict[str, object], ...]:
        """Record explicit REM parameters and fixed-window semantics for replay."""
        return tuple(
            {
                "train_id": train_id,
                "passengers_per_second_per_door": config.passengers_per_second_per_door,
                "doors": config.doors,
                "window": "scheduled_dwell",
                "rounding": "floor",
            }
            for train_id, config in sorted(self.rem_door_throughput.items())
        )

    def decision_records(self) -> tuple[dict[str, Any], ...]:
        """Return the strategy's audit records for ``decisions.jsonl`` (#44)."""
        return self.decision.decision_records()

    def train_states(self) -> tuple[TrainState, ...]:
        """Copy each train's next stop, delay and load for an observation (#38)."""
        return tuple(
            self._train_state(train) for _, train in sorted(self.trains.items())
        )

    def _train_state(self, train: Train) -> TrainState:
        """Copy the vehicle's next visit, load and schedule deviation.

        A train at a platform reports its following stop. Completed service has
        no next stop, while its identity and final onboard load remain available.
        Passenger movements therefore reach controller observations immediately.
        """
        visit = (train.id, train.current_trip_index, train.current_stop_index)
        if visit in self._at_platform[self._stop(visit).platform_id]:
            # A dwelling train's next stop is the following one in its trip
            visit = (*visit[:2], visit[2] + 1)
        load = (train.current_delay, train.onboard_load, train.capacity)
        trip = self._schedules[train.id][visit[1]]
        if train.id in self._finished or visit[2] >= len(trip):
            return TrainState(train.id, train.line_id, None, None, None, *load)
        stop = trip[visit[2]]
        # The arrival the simulator already planned, else timetable + delay
        arrival_s = self._ready_arrivals.get(
            visit, stop.arrival_s + train.current_delay
        )
        next_stop = (stop.platform_id, arrival_s, stop.departure_s)
        return TrainState(train.id, train.line_id, *next_stop, *load)

    def platform_states(self) -> tuple[PlatformState, ...]:
        """Copy waiting counts and last departures per platform (#38)."""
        queue = self.passenger_queue
        return tuple(
            PlatformState(
                platform_id=platform,
                waiting_count=queue.waiting_count(platform) if queue else 0,
                last_departure_s=self._last_departure.get(platform),
            )
            for platform in sorted(self._visits)
        )

    def future_visits(
        self, now_s: float, until_s: float = math.inf
    ) -> tuple[FutureVisit, ...]:
        """Copy remaining visits arriving by ``until_s`` (inclusive seconds).

        Existing holds remain fixed. Return-trip recovery consumes slack once;
        inbound terminals have an arrival but no decision or departure.
        Other strategies never request this potentially larger view.
        No random stream is consumed while copying these values. The observation
        error layer, rather than the train owner, perturbs future predictions.
        Completed vehicles contribute no visits; their identities and final
        loads remain in the existing next-stop view for other controllers.
        The default preserves the complete-route API. A bounded request stops
        each chronological route at its first arrival outside the window.
        """
        return tuple(
            visit
            for train_id, train in sorted(self.trains.items())
            if train_id not in self._finished
            for visit in self._future_train_visits(train, now_s, until_s)
        )

    def _future_train_visits(
        self, train: Train, now_s: float, until_s: float
    ) -> list[FutureVisit]:
        """Project timetable times with current delay and known readiness.

        Fixed holds change later-stop lateness immediately in the view, even
        before HoldEnd updates the live train. At a trip boundary, only the
        unused part of layover can absorb a newly proposed hold. Each return
        starts a distinct trip index even when it reuses the same platform.
        """
        visits = []
        delay = train.current_delay
        for trip_index in range(
            train.current_trip_index, len(self._schedules[train.id])
        ):
            recovery = 0.0
            first_stop = (
                train.current_stop_index
                if trip_index == train.current_trip_index
                else 0
            )
            if trip_index > train.current_trip_index:
                recovery = max(0.0, train.layover_slack - max(0.0, delay))
                delay = max(0.0, delay - train.layover_slack)
            trip = self._schedules[train.id][trip_index]
            for stop_index in range(first_stop, len(trip)):
                key = (train.id, trip_index, stop_index)
                visit = self._future_visit(
                    key, delay, recovery if stop_index == 0 else 0.0, now_s
                )
                if visit.arrival_s > until_s:
                    return visits
                visits.append(visit)
                if not visit.skips_departure:
                    delay = visit.departure_s - visit.scheduled_departure_s
        return visits

    def _future_visit(
        self, key: Visit, delay: float, recovery: float, now_s: float
    ) -> FutureVisit:
        """Copy known timing bounds; future disturbances stay unobserved.

        An arrival already queued has a known separation wait and any already
        scheduled injection. Propagating those bounds prevents an optimistic
        route forecast while preserving the live train's single state owner.
        Already observed arrivals come from the occupied platform's actual
        arrival clock; a later departure-delay update cannot rewrite that past.
        """
        train = self.trains[key[0]]
        stop = self._stop(key)
        arrived = key in self._at_platform[stop.platform_id]
        arrival = self._ready_arrivals.get(key, stop.arrival_s + delay)
        arrival += self._arrival_wait.get(key, 0.0)
        for disruption_id in self._disruptions_by_arrival.get(key, ()):
            arrival = max(
                arrival, self._scheduled_disruptions[disruption_id]["arrival_time_s"]
            )
        if arrived:
            arrival = self._last_arrival[stop.platform_id]
        departure = self._ready_departures.get(
            key,
            arrival + stop.departure_s - stop.arrival_s + self._hold_s.get(key, 0.0),
        )
        skips = key[2] == len(self._schedules[train.id][key[1]]) - 1 and key[1] < len(
            train.return_trips
        )
        return FutureVisit(
            train.id,
            key[1],
            key[2],
            stop.station_id,
            stop.platform_id,
            arrival,
            max(now_s, departure) if not skips else arrival,
            stop.arrival_s,
            stop.departure_s,
            key not in self._hold_s and key not in self._ready_departures and not skips,
            skips,
            recovery,
            arrived,
            self._last_arrival.get(stop.platform_id, -self.minimum_gap_s)
            + self.minimum_gap_s,
        )

    def handle(self, event: Event, scheduler: Scheduler) -> None:
        """Process train movement, dispatch restrictions and passenger arrivals."""
        if isinstance(event, TrainArrival):
            self._on_arrival(event, scheduler)
        elif isinstance(event, DepartureDue):
            self._on_due(event, scheduler)
        elif isinstance(event, HoldEnd):
            self._on_hold_end(event, scheduler)
        elif isinstance(event, DepartureClearance):
            self._on_clearance(event, scheduler)
        elif isinstance(event, TrainDeparture):
            self._on_departure(event, scheduler)
        elif isinstance(event, Alighting) and self.passenger_queue is not None:
            self.passenger_queue.external_alighting(event)
        elif isinstance(event, PassengerArrival) and self.passenger_queue is not None:
            if self.passenger_queue.arrive(event):
                for missed in self.passenger_queue.late_arrival(event):
                    scheduler.schedule(missed)
                self._board_waiting(event.platform_id, event.time_s, scheduler)

    def _board_waiting(
        self, platform: str, time_s: float, scheduler: Scheduler
    ) -> None:
        """Board once through the queue and record actual movement events.

        The queue updates live load before a departure decision can read it.
        Capacity released by destination alighting is already available here.
        Per-visit counts include arrivals during holds and dispatch waits.
        """
        if self.passenger_queue is None:
            return
        for visit in self._at_platform[platform]:
            train = self.trains[visit[0]]
            config = self.rem_door_throughput.get(train.id)
            remaining = None
            if config is not None:
                stop = self._stop(visit)
                total = config.budget(stop.departure_s - stop.arrival_s)
                remaining = max(0, total - self._boarded[visit])
            passenger_ids = self.passenger_queue.board(
                platform, train, max_boarding=remaining
            )
            self._boarded[visit] += len(passenger_ids)
            for passenger_id in passenger_ids:
                scheduler.schedule(
                    Boarding(
                        time_s=time_s,
                        passenger_id=passenger_id,
                        train_id=train.id,
                        platform_id=platform,
                    )
                )

    def _on_arrival(self, event: TrainArrival, scheduler: Scheduler) -> None:
        """Open this visit and alight destination passengers before boarding.

        Alighting happens before terminal recovery mutates the current trip.
        Its records retain the inbound platform, including at a terminus with
        no inbound departure. The next trip starts fresh passenger counts.
        """
        train = self.trains.get(event.train_id)
        if train is None:
            return
        visit = (train.id, train.current_trip_index, train.current_stop_index)
        platform = event.platform_id
        if visit != self._next_visit(platform, self._arrival_cursor):
            raise RuntimeError("Train arrival violates platform order")
        if platform in self._occupied_platforms:
            raise RuntimeError("Train arrival attempted to occupy a busy platform")
        self._occupied_platforms[platform] = visit
        self._applied_disruptions.update(self._disruptions_by_arrival.pop(visit, ()))
        train.update_delay(
            actual_s=event.time_s,
            scheduled_s=self._stop(visit).arrival_s,
            inherited_wait_s=self._arrival_wait.pop(visit, 0.0),
        )
        self._last_arrival[platform] = event.time_s
        self._arrival_cursor[platform] += 1
        self._arrival_queued.discard(visit)
        stop = self._stop(visit)

        if self.passenger_queue is not None:
            for alighting in self.passenger_queue.train_arrival(event, train):
                scheduler.schedule(alighting)

        if visit[2] == len(
            self._schedules[train.id][visit[1]]
        ) - 1 and train.current_trip_index < len(train.return_trips):
            del self._occupied_platforms[platform]
            self._release_arrival(platform, scheduler)
            self._skip_departure(visit, platform, scheduler)
            ready_s = train.begin_return_trip()
            if ready_s is None:
                raise RuntimeError("Expected a configured return trip")
            next_trip = train.current_trip_index
            self._register_trip_visits(train.id, next_trip)
            for next_platform in {
                item.platform_id for item in self._schedules[train.id][next_trip]
            }:
                self._sort_pending_visits(next_platform, self._arrival_cursor)
                self._sort_pending_visits(next_platform, self._departure_cursor)
            next_visit = (train.id, next_trip, 0)
            self._ready_arrivals[next_visit] = ready_s
            self._release_arrival(self._stop(next_visit).platform_id, scheduler)
            return

        self._at_platform[platform].append(visit)
        self._boarded[visit] = 0
        self._board_waiting(platform, event.time_s, scheduler)
        dwell_s = stop.departure_s - stop.arrival_s
        # Waiting for the timetable belongs to the selected strategy.
        due_s = event.time_s + dwell_s
        scheduler.schedule(
            DepartureDue(
                time_s=due_s,
                train_id=train.id,
                station_id=stop.station_id,
                platform_id=platform,
                scheduled_s=stop.departure_s,
            )
        )

    def _skip_departure(
        self, visit: Visit, platform: str, scheduler: Scheduler
    ) -> None:
        """Clear a terminal's inbound visit without inventing a departure.

        Actual departures belong to the configured return trip. Followers can
        proceed after the inbound vehicle releases its occupied platform.
        """
        self._skipped_departures.add(visit)
        self._advance_skipped_departures(platform)
        self._release_departure(platform, scheduler)

    def _advance_skipped_departures(self, platform: str) -> None:
        """Advance over terminal visits that have no physical departure.

        A skipped visit may become the cursor head after a preceding vehicle
        leaves, so clearance is checked again whenever departures are released.
        """
        while (
            self._next_visit(platform, self._departure_cursor)
            in self._skipped_departures
        ):
            skipped = self._next_visit(platform, self._departure_cursor)
            if skipped is None:
                return
            self._skipped_departures.remove(skipped)
            self._departure_cursor[platform] += 1

    def _on_due(self, event: DepartureDue, scheduler: Scheduler) -> None:
        """Ask the controller after same-time boarding is known.

        Positive holds defer readiness until HoldEnd, keeping doors open.
        A duplicate decision for the same visit raises RuntimeError rather than
        scheduling two holds or recording inconsistent departure counts.
        Platform arrivals at this instant have already used any available seats.
        """
        train = self.trains.get(event.train_id)
        if train is None:
            return
        visit = (train.id, train.current_trip_index, train.current_stop_index)
        if visit in self._ready_departures or visit in self._hold_s:
            raise RuntimeError("Duplicate DepartureDue event")
        train.update_delay(actual_s=event.time_s, scheduled_s=event.scheduled_s)
        hold = self.decision.decide(event, self)
        if hold is not None:
            where = {
                "train_id": train.id,
                "station_id": event.station_id,
                "platform_id": event.platform_id,
            }
            scheduler.schedule(
                Hold(
                    time_s=event.time_s,
                    requested_s=hold.requested_s,
                    applied_s=hold.applied_s,
                    reason=hold.reason,
                    **where,
                )
            )
            if hold.applied_s > 0:
                # Task 2.4.4 (#53): Flag train as system-delayed
                # when a hold is successfully applied
                train.system_delayed = True
                # The train leaves at HoldEnd, still subject to the minimum gap
                self._hold_s[visit] = hold.applied_s
                self._unheld_ready_s[visit] = event.time_s
                scheduler.schedule(
                    HoldEnd(time_s=event.time_s + hold.applied_s, **where)
                )
                return
        self._ready_departures[visit] = event.time_s
        self._release_departure(event.platform_id, scheduler)

    def _on_hold_end(self, event: HoldEnd, scheduler: Scheduler) -> None:
        """End the policy hold and recheck physical departure constraints.

        Boarding at this exact instant sorts before HoldEnd. A dispatch or
        minimum-gap wait can still postpone the actual closing of the doors.
        """
        train = self.trains[event.train_id]
        visit = (train.id, train.current_trip_index, train.current_stop_index)
        self._ready_departures[visit] = event.time_s
        self._release_departure(event.platform_id, scheduler)

    def _release_departure(self, platform: str, scheduler: Scheduler) -> None:
        """Build departure records only when the vehicle can actually leave.

        Dispatch suspension and minimum gaps can extend the boarding window.
        Future clearance events contain no passenger counts; final boarding,
        alighting and load are copied only at the real departure time.
        A hold's duration stays distinct from additional platform-spacing delay.
        """
        self._advance_skipped_departures(platform)
        visit = self._next_visit(platform, self._departure_cursor)
        if (
            visit is None
            or visit not in self._ready_departures
            or visit in self._departure_queued
            or visit in self._clearance_queued
        ):
            return
        ready_s = self._ready_departures[visit]
        train = self.trains[visit[0]]
        stop = self._stop(visit)
        dispatch_s = ready_s
        if visit[2] == 0:
            dispatch_s = dispatch_ready_s(train.line_id, ready_s, self.suspensions)
        safe_s = max(
            dispatch_s,
            scheduler.now,
            self._last_departure.get(platform, -math.inf) + self.minimum_gap_s,
        )
        if safe_s > scheduler.now:
            scheduler.schedule(
                DepartureClearance(
                    time_s=safe_s,
                    train_id=train.id,
                    station_id=stop.station_id,
                    platform_id=platform,
                )
            )
            self._clearance_queued.add(visit)
            return
        self._record_departure(visit, safe_s, scheduler)

    def _record_departure(
        self, visit: Visit, actual_s: float, scheduler: Scheduler
    ) -> None:
        train = self.trains[visit[0]]
        stop = self._stop(visit)
        # Keep the original time to avoid rounding errors at suspension boundaries.
        ready_s = self._unheld_ready_s.pop(visit, self._ready_departures[visit])
        # Check when dispatch would be allowed without the hold.
        dispatch_s = ready_s
        if visit[2] == 0:
            dispatch_s = dispatch_ready_s(train.line_id, ready_s, self.suspensions)
        clearance_s = max(
            dispatch_s,
            self._last_departure.get(stop.platform_id, -math.inf) + self.minimum_gap_s,
        )
        # Early waiting contributes no lateness.
        dispatch_delay = max(0.0, dispatch_s - stop.departure_s)
        clearance_delay = max(0.0, clearance_s - stop.departure_s)
        # Split delay between train separation and extra holding.
        train.update_delay(
            actual_s=actual_s,
            scheduled_s=stop.departure_s,
            inherited_wait_s=clearance_delay - dispatch_delay,
            hold_delay_s=max(0.0, actual_s - stop.departure_s) - clearance_delay,
        )
        scheduler.schedule(
            TrainDeparture(
                time_s=actual_s,
                train_id=train.id,
                station_id=stop.station_id,
                platform_id=stop.platform_id,
                scheduled_s=stop.departure_s,
                disruption_delay_s=train.disruption_delay_s,
                hold_s=self._hold_s.pop(visit, 0.0),
                boarded_count=self._boarded[visit],
                alighted_count=(
                    self.passenger_queue.alighted_count(train.id)
                    if self.passenger_queue is not None
                    else 0
                ),
                onboard_load=train.onboard_load,
                generated_delay_s=train.generated_delay_s,
                inherited_delay_s=train.inherited_delay_s,
            )
        )
        self._departure_queued.add(visit)

    def _on_clearance(self, event: DepartureClearance, scheduler: Scheduler) -> None:
        """Reconsider a waiting departure without duplicating its clearance.

        The platform may still be constrained by a suspension or a predecessor.
        Only the final release constructs the departure and its passenger counts.
        """
        train = self.trains.get(event.train_id)
        if train is None:
            return
        visit = (train.id, train.current_trip_index, train.current_stop_index)
        self._clearance_queued.remove(visit)
        self._release_departure(event.platform_id, scheduler)

    def _on_departure(self, event: TrainDeparture, scheduler: Scheduler) -> None:
        """Close doors, mark missed connections, then advance the vehicle.

        The queue snapshots the departing route before the stop index changes.
        Passenger arrivals processed later can then identify the service missed.
        Followers are released only after occupancy and both cursors agree.
        Per-stop counts reset at the next arrival; through passengers keep seats.
        The same vehicle may revisit a platform on a later configured trip.
        Those departures remain distinct entries in passenger connection history.
        """
        train = self.trains.get(event.train_id)
        if train is None:
            return
        visit = (train.id, train.current_trip_index, train.current_stop_index)
        platform = event.platform_id
        self._advance_skipped_departures(platform)
        if visit != self._next_visit(platform, self._departure_cursor):
            raise RuntimeError("Train departure violates platform order")
        if self.passenger_queue is not None:
            for missed in self.passenger_queue.train_departure(event, train):
                scheduler.schedule(missed)
        current_stop = self._stop(visit)
        self._last_departure[platform] = event.time_s
        if self._occupied_platforms.pop(platform, None) != visit:
            raise RuntimeError("Train departure does not own its platform")
        self._departure_cursor[platform] += 1
        self._departure_queued.discard(visit)
        self._ready_departures.pop(visit, None)
        self._at_platform[platform].remove(visit)

        if train.advance_stop():
            next_visit = (train.id, train.current_trip_index, train.current_stop_index)
            next_stop = self._stop(next_visit)
            travel_s = next_stop.arrival_s - current_stop.departure_s
            if travel_s <= 0:
                raise ValueError("Inter-station travel time must be positive")
            # Actual departure determines natural arrival; platform separation
            # is enforced by _release_arrival, independently of the timetable.
            self._ready_arrivals[next_visit] = event.time_s + travel_s
            self._release_arrival(next_stop.platform_id, scheduler)
        else:
            self._finished.add(train.id)
        self._release_arrival(platform, scheduler)
        self._release_departure(platform, scheduler)
