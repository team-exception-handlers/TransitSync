# AI contribution: 50% or more AI-generated
"""Connect trains, passenger queues and disruptions to the event engine."""

import math
from collections import defaultdict, deque
from collections.abc import Sequence
from typing import Any

from simulator.control.decision import DecisionPipeline
from simulator.control.interface import PlatformState, TrainState
from simulator.engine.event_queue import Scheduler
from simulator.engine.events import (
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
    ) -> None:
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
        if passenger_queue is not None and not isinstance(
            passenger_queue, PlatformQueue
        ):
            raise ValueError("passenger_queue must be a PlatformQueue")
        self.passenger_queue = passenger_queue
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

    def _stop(self, visit: Visit) -> ScheduledStop:
        train_id, trip_index, stop_index = visit
        return self._schedules[train_id][trip_index][stop_index]

    def _visit_sort_key(self, visit: Visit) -> tuple[float, str, int, int]:
        return (self._stop(visit).arrival_s, visit[0], visit[1], visit[2])

    def _register_trip_visits(self, train_id: str, trip_index: int) -> None:
        for stop_index, stop in enumerate(self._schedules[train_id][trip_index]):
            self._visits[stop.platform_id].append((train_id, trip_index, stop_index))
            self._arrival_cursor.setdefault(stop.platform_id, 0)
            self._departure_cursor.setdefault(stop.platform_id, 0)

    def _next_visit(self, platform: str, cursors: dict[str, int]) -> Visit | None:
        index = cursors[platform]
        visits = self._visits[platform]
        return visits[index] if index < len(visits) else None

    def _sort_pending_visits(self, platform: str, cursor: dict[str, int]) -> None:
        visits = self._visits[platform]
        index = cursor[platform]
        visits[index:] = sorted(visits[index:], key=self._visit_sort_key)

    def start(self, scheduler: Scheduler) -> None:
        """Schedule the first arrival for each train."""
        for train in self.trains.values():
            first_stop = self._schedules[train.id][0][0]
            self._ready_arrivals[(train.id, 0, 0)] = max(
                0.0, first_stop.arrival_s + max(0.0, train.current_delay)
            )
        for platform in sorted(self._visits):
            self._release_arrival(platform, scheduler)

    def _release_arrival(self, platform: str, scheduler: Scheduler) -> None:
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
                disruption_delay_s=train.generated_delay_s + injected_s,
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

    def decision_records(self) -> tuple[dict[str, Any], ...]:
        """Return the strategy's audit records for ``decisions.jsonl`` (#44)."""
        return self.decision.decision_records()

    def train_states(self) -> tuple[TrainState, ...]:
        """Copy each train's next stop, delay and load for an observation (#38)."""
        return tuple(
            self._train_state(train) for _, train in sorted(self.trains.items())
        )

    def _train_state(self, train: Train) -> TrainState:
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
            visit, stop.arrival_s + max(0.0, train.current_delay)
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
        elif isinstance(event, PassengerArrival) and self.passenger_queue is not None:
            if self.passenger_queue.arrive(event):
                self._board_waiting(event.platform_id, event.time_s, scheduler)

    def _board_waiting(
        self, platform: str, time_s: float, scheduler: Scheduler
    ) -> None:
        if self.passenger_queue is None:
            return
        for visit in self._at_platform[platform]:
            train = self.trains[visit[0]]
            passenger_ids = self.passenger_queue.board(platform, train)
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
        due_s = max(stop.departure_s, event.time_s + dwell_s)
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
        self._skipped_departures.add(visit)
        self._advance_skipped_departures(platform)
        self._release_departure(platform, scheduler)

    def _advance_skipped_departures(self, platform: str) -> None:
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
                # The train leaves at HoldEnd, still subject to the minimum gap
                self._hold_s[visit] = hold.applied_s
                scheduler.schedule(
                    HoldEnd(time_s=event.time_s + hold.applied_s, **where)
                )
                return
        self._ready_departures[visit] = event.time_s
        self._release_departure(event.platform_id, scheduler)

    def _on_hold_end(self, event: HoldEnd, scheduler: Scheduler) -> None:
        train = self.trains[event.train_id]
        visit = (train.id, train.current_trip_index, train.current_stop_index)
        self._ready_departures[visit] = event.time_s
        self._release_departure(event.platform_id, scheduler)

    def _release_departure(self, platform: str, scheduler: Scheduler) -> None:
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
        inherited_wait_s = max(0.0, safe_s - dispatch_s)
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
        train.update_delay(
            actual_s=safe_s,
            scheduled_s=stop.departure_s,
            inherited_wait_s=inherited_wait_s,
        )
        scheduler.schedule(
            TrainDeparture(
                time_s=safe_s,
                train_id=train.id,
                station_id=stop.station_id,
                platform_id=platform,
                scheduled_s=stop.departure_s,
                disruption_delay_s=train.generated_delay_s,
                hold_s=self._hold_s.pop(visit, 0.0),
                boarded_count=self._boarded[visit],
                alighted_count=0,
                onboard_load=train.onboard_load,
                generated_delay_s=train.generated_delay_s,
                inherited_delay_s=train.inherited_delay_s,
            )
        )
        self._departure_queued.add(visit)

    def _on_clearance(self, event: DepartureClearance, scheduler: Scheduler) -> None:
        train = self.trains.get(event.train_id)
        if train is None:
            return
        visit = (train.id, train.current_trip_index, train.current_stop_index)
        self._clearance_queued.remove(visit)
        self._release_departure(event.platform_id, scheduler)

    def _on_departure(self, event: TrainDeparture, scheduler: Scheduler) -> None:
        train = self.trains.get(event.train_id)
        if train is None:
            return
        visit = (train.id, train.current_trip_index, train.current_stop_index)
        platform = event.platform_id
        self._advance_skipped_departures(platform)
        if visit != self._next_visit(platform, self._departure_cursor):
            raise RuntimeError("Train departure violates platform order")
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
            self._ready_arrivals[next_visit] = max(
                next_stop.arrival_s, event.time_s + travel_s
            )
            self._release_arrival(next_stop.platform_id, scheduler)
        else:
            self._finished.add(train.id)
        self._release_arrival(platform, scheduler)
        self._release_departure(platform, scheduler)
