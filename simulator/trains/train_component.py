# AI contribution: 50% or more AI-generated
"""Connect generated trains to the deterministic event engine."""

import math
from bisect import insort
from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import replace

from simulator.engine.event_queue import Scheduler
from simulator.engine.events import (
    Boarding,
    DepartureDue,
    Event,
    PassengerArrival,
    TrainArrival,
    TrainDeparture,
)
from simulator.passengers.platform_queue import PlatformQueue
from simulator.trains.suspension import LineSuspension, dispatch_ready_s
from simulator.trains.train import Train


class TrainComponent:
    """Owns train objects for the entire simulation run."""

    def __init__(
        self,
        trains: Sequence[Train],
        minimum_gap_s: float = 90.0,
        *,
        suspensions: Sequence[LineSuspension] = (),
        passenger_queue: PlatformQueue | None = None,
    ) -> None:
        if not math.isfinite(minimum_gap_s) or minimum_gap_s <= 0:
            raise ValueError("Minimum gap must be finite and positive")
        self.minimum_gap_s = minimum_gap_s
        self.trains: dict[str, Train] = {}
        self.suspensions = tuple(suspensions)
        if any(not isinstance(item, LineSuspension) for item in self.suspensions):
            raise ValueError("Suspensions must be LineSuspension instances")
        self.passenger_queue = passenger_queue
        self._reserved_arrival: dict[str, list[float]] = defaultdict(list)
        self._last_departure: dict[str, float] = {}
        self._at_platform: dict[str, deque[str]] = defaultdict(deque)
        self._departure_ready: dict[str, float] = {}
        self._boarded: dict[str, int] = defaultdict(int)

        for train in trains:
            if train.id in self.trains:
                raise ValueError(f"Duplicate train ID: {train.id}")

            self.trains[train.id] = train
        if self.suspensions and any(not train.line_id.strip() for train in trains):
            raise ValueError("Trains need explicit line IDs when suspensions are used")

    def start(self, scheduler: Scheduler) -> None:
        """Schedule the first arrival of each train"""
        ordered_trains = sorted(
            self.trains.values(),
            key=lambda train: (
                train.schedule[0].arrival_s,
                train.id,
            ),
        )

        previous_initial: dict[str, float] = {}
        for train in ordered_trains:
            train.generated_delay_s = max(0.0, train.current_delay)
            platform = train.current_stop.platform_id
            previous_initial[platform] = self._schedule_arrival(
                train,
                train.current_stop.arrival_s + train.generated_delay_s,
                scheduler,
                not_before_s=previous_initial.get(platform, -self.minimum_gap_s)
                + self.minimum_gap_s,
            )

    def _schedule_arrival(
        self,
        train: Train,
        natural_s: float,
        scheduler: Scheduler,
        *,
        not_before_s: float = 0.0,
    ) -> float:
        """Reserve the earliest safe slot, respecting earlier AND later bookings."""
        stop = train.current_stop
        reservations = self._reserved_arrival[stop.platform_id]
        safe_s = max(natural_s, not_before_s)
        for reserved_s in reservations:
            if safe_s + self.minimum_gap_s <= reserved_s:
                break
            safe_s = max(safe_s, reserved_s + self.minimum_gap_s)
        insort(reservations, safe_s)
        train.inherited_delay_s += safe_s - natural_s
        scheduler.schedule(
            TrainArrival(
                time_s=safe_s,
                train_id=train.id,
                station_id=stop.station_id,
                platform_id=stop.platform_id,
                scheduled_s=stop.arrival_s,
                disruption_delay_s=train.generated_delay_s,
            )
        )
        return safe_s

    def handle(self, event: Event, scheduler: Scheduler) -> None:
        """Process train movement and optional platform waiting events."""
        if isinstance(event, TrainArrival):
            self._handle_arrival(event, scheduler)

        elif isinstance(event, DepartureDue):
            self._handle_departure_due(event, scheduler)

        elif isinstance(event, TrainDeparture):
            self._handle_departure(event, scheduler)
        elif isinstance(event, PassengerArrival) and self.passenger_queue is not None:
            if self.passenger_queue.arrive(event):
                self._board_waiting(event.platform_id, event.time_s, scheduler)

    def _board_waiting(
        self, platform_id: str, time_s: float, scheduler: Scheduler
    ) -> None:
        if self.passenger_queue is None:
            return
        for train_id in self._at_platform[platform_id]:
            train = self.trains[train_id]
            passengers = self.passenger_queue.board(platform_id, train)
            self._boarded[train_id] += len(passengers)
            for passenger_id in passengers:
                scheduler.schedule(
                    Boarding(
                        time_s=time_s,
                        passenger_id=passenger_id,
                        train_id=train_id,
                        platform_id=platform_id,
                    )
                )

    def _handle_arrival(
        self,
        event: TrainArrival,
        scheduler: Scheduler,
    ) -> None:
        train = self.trains.get(event.train_id)

        if train is None:
            return

        stop = train.current_stop

        dwell_s = stop.departure_s - stop.arrival_s

        due_time = max(
            stop.departure_s,
            event.time_s + dwell_s,
        )

        train.update_delay(
            actual_s=event.time_s,
            scheduled_s=stop.arrival_s,
        )

        # The inbound trip ends at its terminal arrival. Its next departure
        # belongs to the return trip, so do not emit a fictitious departure
        # before the layover. Scheduling here also permits zero remaining
        # turnaround without violating the engine's same-time tie order.
        if train.current_stop_index == len(
            train.schedule
        ) - 1 and train.current_trip_index < len(train.return_trips):
            ready_s = train.begin_return_trip()
            assert ready_s is not None
            self._schedule_arrival(train, ready_s, scheduler)
            return

        self._at_platform[stop.platform_id].append(train.id)
        self._departure_ready[train.id] = due_time
        self._boarded[train.id] = 0
        self._board_waiting(stop.platform_id, event.time_s, scheduler)

        scheduler.schedule(
            DepartureDue(
                time_s=due_time,
                train_id=train.id,
                station_id=stop.station_id,
                platform_id=stop.platform_id,
                scheduled_s=stop.departure_s,
            )
        )

    def _handle_departure_due(
        self,
        event: DepartureDue,
        scheduler: Scheduler,
    ) -> None:
        train = self.trains.get(event.train_id)

        if train is None:
            return

        platform = event.platform_id
        safe_time = event.time_s

        # Dispatch is the first departure of EACH trip; in-flight trips continue.
        if train.current_stop_index == 0:
            ready_s = dispatch_ready_s(train.line_id, safe_time, self.suspensions)
            train.generated_delay_s += ready_s - safe_time
            safe_time = ready_s

        leader_id = self._at_platform[platform][0]
        if leader_id != train.id:
            safe_time = max(
                safe_time, self._departure_ready[leader_id] + self.minimum_gap_s
            )

        if platform in self._last_departure:
            safe_time = max(
                safe_time,
                self._last_departure[platform] + self.minimum_gap_s,
            )

        self._departure_ready[train.id] = safe_time

        if safe_time > event.time_s:
            scheduler.schedule(replace(event, time_s=safe_time))
            return

        # Reserve now: another DepartureDue at this timestamp must see it.
        self._last_departure[platform] = safe_time
        scheduler.schedule(
            TrainDeparture(
                time_s=event.time_s,
                train_id=train.id,
                station_id=event.station_id,
                platform_id=platform,
                scheduled_s=event.scheduled_s,
                disruption_delay_s=train.generated_delay_s,
                hold_s=0.0,
                boarded_count=self._boarded[train.id],
                alighted_count=0,
                onboard_load=train.onboard_load,
            )
        )

    def _handle_departure(
        self,
        event: TrainDeparture,
        scheduler: Scheduler,
    ) -> None:
        train = self.trains.get(event.train_id)

        if train is None:
            return

        self._last_departure[event.platform_id] = event.time_s
        self._at_platform[event.platform_id].remove(train.id)
        self._departure_ready.pop(train.id, None)

        current_stop = train.current_stop

        train.update_delay(
            actual_s=event.time_s,
            scheduled_s=current_stop.departure_s,
        )
        train.inherited_delay_s = max(
            0.0, train.current_delay - train.generated_delay_s
        )

        if not train.advance_stop():
            return
        next_stop = train.current_stop
        travel_s = next_stop.arrival_s - current_stop.departure_s
        next_arrival_s = max(next_stop.arrival_s, event.time_s + travel_s)
        self._schedule_arrival(train, next_arrival_s, scheduler)
