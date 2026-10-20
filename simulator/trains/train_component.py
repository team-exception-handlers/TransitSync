# AI contribution: 50% or more AI-generated
"""Connect generated trains to the deterministic event engine.
Enforces minimum-gap"""

import math
from collections import defaultdict
from collections.abc import Sequence

from simulator.engine.event_queue import Scheduler
from simulator.engine.events import (
    DepartureClearance,
    DepartureDue,
    Event,
    TrainArrival,
    TrainDeparture,
)
from simulator.trains.train import Train

Visit = tuple[str, int]  # train ID and index of stop in its schedule


class TrainComponent:
    """Owns train objects for the entire simulation run."""

    def __init__(
        self,
        trains: Sequence[Train],
        minimum_gap_s: float = 90.0,
    ) -> None:
        if not math.isfinite(minimum_gap_s) or minimum_gap_s <= 0:
            raise ValueError("Minimum gap must be finite and positive")

        self.minimum_gap_s = minimum_gap_s
        self.trains: dict[str, Train] = {}

        self._visits: dict[str, list[Visit]] = defaultdict(list)

        for train in trains:
            if train.id in self.trains:
                raise ValueError(f"Duplicate train ID: {train.id}")

            self.trains[train.id] = train

            for index, stop in enumerate(train.schedule):
                self._visits[stop.platform_id].append((train.id, index))
        for _platform, visits in self._visits.items():
            visits.sort(
                key=lambda visit: (
                    self.trains[visit[0]].schedule[visit[1]].arrival_s,
                    visit[0],
                    visit[1],
                )
            )
        self._arrival_cursor = {platform: 0 for platform in self._visits}
        self._departure_cursor = {platform: 0 for platform in self._visits}

        self._ready_arrivals: dict[Visit, float] = {}
        self._ready_departures: dict[Visit, float] = {}

        self._arrival_queued: set[Visit] = set()
        self._departure_queued: set[Visit] = set()
        self._clearance_queued: set[Visit] = set()

        self._last_arrival: dict[str, float] = {}
        self._last_departure: dict[str, float] = {}

    def _next_visit(self, platform: str, cursors: dict[str, int]) -> Visit | None:
        """Return the next train visit in platform order"""
        index = cursors[platform]
        visits = self._visits[platform]

        if index >= len(visits):
            return None

        return visits[index]

    def start(self, scheduler: Scheduler) -> None:
        """Schedule the first arrival of each train"""

        for train in self.trains.values():
            stop = train.schedule[0]

            self._ready_arrivals[(train.id, 0)] = max(
                0.0, stop.arrival_s + train.current_delay
            )

        for platform in sorted(self._visits):
            self._release_arrival(platform, scheduler)

    def _release_arrival(self, platform: str, scheduler: Scheduler) -> None:
        """Schedule only the next eligible platform arrival"""

        visit = self._next_visit(platform, self._arrival_cursor)

        if (
            visit is None
            or visit not in self._ready_arrivals
            or visit in self._arrival_queued
        ):
            return

        train = self.trains[visit[0]]
        stop = train.schedule[visit[1]]

        requested_s = self._ready_arrivals[visit]

        safe_s = max(
            requested_s,
            self._last_arrival.get(platform, -math.inf) + self.minimum_gap_s,
        )

        scheduler.schedule(
            TrainArrival(
                time_s=safe_s,
                train_id=train.id,
                station_id=stop.station_id,
                platform_id=platform,
                scheduled_s=stop.arrival_s,
                disruption_delay_s=0.0,
            )
        )

        self._arrival_queued.add(visit)

    def handle(self, event: Event, scheduler: Scheduler) -> None:
        """Process arrivals, departure decisions and departues"""
        if isinstance(event, TrainArrival):
            self._on_arrival(event, scheduler)

        elif isinstance(event, DepartureDue):
            self._on_due(event, scheduler)

        elif isinstance(event, DepartureClearance):
            self._on_clearance(event, scheduler)

        elif isinstance(event, TrainDeparture):
            self._on_departure(event, scheduler)

    def _on_arrival(
        self,
        event: TrainArrival,
        scheduler: Scheduler,
    ) -> None:
        train = self.trains.get(event.train_id)

        if train is None:
            return

        visit = (train.id, train.current_stop_index)
        platform = event.platform_id

        expected = self._next_visit(platform, self._arrival_cursor)

        if visit != expected:
            raise RuntimeError("train arrival violates platform order")

        stop = train.current_stop
        requested_s = self._ready_arrivals[visit]

        train.update_delay(
            actual_s=event.time_s,
            scheduled_s=stop.arrival_s,
            inherited_wait_s=max(
                0.0,
                event.time_s - requested_s,
            ),
        )

        self._last_arrival[platform] = event.time_s
        self._arrival_cursor[platform] += 1

        self._release_arrival(platform, scheduler)

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

    def _on_due(
        self,
        event: DepartureDue,
        scheduler: Scheduler,
    ) -> None:
        train = self.trains.get(event.train_id)

        if train is None:
            return

        visit = (train.id, train.current_stop_index)

        if visit in self._ready_departures:
            raise RuntimeError("Duplicate DepartureDue event")

        train.update_delay(actual_s=event.time_s, scheduled_s=event.scheduled_s)

        self._ready_departures[visit] = event.time_s

        self._release_departure(event.platform_id, scheduler)

    def _release_departure(self, platform: str, scheduler: Scheduler) -> None:
        """Authorize departures in physcial order"""

        visit = self._next_visit(platform, self._departure_cursor)

        if (
            visit is None
            or visit not in self._ready_departures
            or visit in self._departure_queued
            or visit in self._clearance_queued
        ):
            return

        ready_s = self._ready_departures[visit]

        safe_s = max(
            ready_s,
            scheduler.now,
            self._last_departure.get(platform, -math.inf) + self.minimum_gap_s,
        )

        train = self.trains[visit[0]]
        stop = train.schedule[visit[1]]

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
            actual_s=scheduler.now,
            scheduled_s=stop.departure_s,
            inherited_wait_s=max(0.0, scheduler.now - ready_s),
        )

        scheduler.schedule(
            TrainDeparture(
                time_s=scheduler.now,
                train_id=train.id,
                station_id=stop.station_id,
                platform_id=platform,
                scheduled_s=stop.departure_s,
                disruption_delay_s=0.0,
                hold_s=0.0,
                boarded_count=0,
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

        visit = (train.id, train.current_stop_index)
        self._clearance_queued.remove(visit)

        self._release_departure(event.platform_id, scheduler)

    def _on_departure(
        self,
        event: TrainDeparture,
        scheduler: Scheduler,
    ) -> None:
        train = self.trains.get(event.train_id)

        if train is None:
            return

        visit = (train.id, train.current_stop_index)
        platform = event.platform_id

        expected = self._next_visit(platform, self._departure_cursor)

        if visit != expected:
            raise RuntimeError("Train departure violates platform order")

        current_stop = train.current_stop

        self._last_departure[platform] = event.time_s
        self._departure_cursor[platform] += 1

        if train.advance_stop():
            next_stop = train.current_stop

            travel_s = next_stop.arrival_s - current_stop.departure_s

            if travel_s <= 0:
                raise ValueError("Inter-station travel time must be positive")

            requested_s = max(next_stop.arrival_s, event.time_s + travel_s)

            next_visit = (train.id, train.current_stop_index)

            self._ready_arrivals[next_visit] = requested_s
            self._release_arrival(next_stop.platform_id, scheduler)
        self._release_departure(platform, scheduler)
