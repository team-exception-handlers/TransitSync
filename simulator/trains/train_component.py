# AI contribution: 50% or more AI-generated
"""Connect generated trains to the deterministic event engine."""

import math
from collections.abc import Sequence

from simulator.engine.event_queue import Scheduler
from simulator.engine.events import DepartureDue, Event, TrainArrival, TrainDeparture
from simulator.trains.train import Train


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

        self._reserved_arrival: dict[str, float] = {}

        self._last_departure: dict[str, float] = {}

        for train in trains:
            if train.id in self.trains:
                raise ValueError(f"Duplicate train ID: {train.id}")

            self.trains[train.id] = train

    def start(self, scheduler: Scheduler) -> None:
        """Schedule the first arrival of each train"""
        ordered_trains = sorted(
            self.trains.values(),
            key=lambda train: (
                train.schedule[0].arrival_s,
                train.id,
            ),
        )

        for train in ordered_trains:
            stop = train.schedule[0]
            platform = stop.platform_id

            safe_time = stop.arrival_s

            if platform in self._reserved_arrival:
                safe_time = max(
                    safe_time,
                    self._reserved_arrival[platform] + self.minimum_gap_s,
                )

            self._reserved_arrival[platform] = safe_time

            scheduler.schedule(
                TrainArrival(
                    time_s=safe_time,
                    train_id=train.id,
                    station_id=stop.station_id,
                    platform_id=platform,
                    scheduled_s=stop.arrival_s,
                    disruption_delay_s=0.0,
                )
            )

    def handle(self, event: Event, scheduler: Scheduler) -> None:
        """Process arrivals, departure decisions and departues"""
        if isinstance(event, TrainArrival):
            self._handle_arrival(event, scheduler)

        elif isinstance(event, DepartureDue):
            self._handle_departure_due(event, scheduler)

        elif isinstance(event, TrainDeparture):
            self._handle_departure(event, scheduler)

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

        if platform in self._last_departure:
            safe_time = max(
                safe_time,
                self._last_departure[platform] + self.minimum_gap_s,
            )

        if safe_time > event.time_s:
            scheduler.schedule(
                DepartureDue(
                    time_s=safe_time,
                    train_id=event.train_id,
                    station_id=event.station_id,
                    platform_id=platform,
                    scheduled_s=event.scheduled_s,
                )
            )
            return

        scheduler.schedule(
            TrainDeparture(
                time_s=event.time_s,
                train_id=train.id,
                station_id=event.station_id,
                platform_id=platform,
                scheduled_s=event.scheduled_s,
                disruption_delay_s=0.0,
                hold_s=0.0,
                boarded_count=0,
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

        current_stop = train.current_stop

        train.update_delay(
            actual_s=event.time_s,
            scheduled_s=current_stop.departure_s,
        )

        if not train.advance_stop():
            return

        next_stop = train.current_stop

        travel_s = next_stop.arrival_s - current_stop.departure_s

        next_arrival_s = max(
            next_stop.arrival_s,
            event.time_s + travel_s,
        )

        previous = self._reserved_arrival.get(next_stop.platform_id)

        if previous is not None:
            next_arrival_s = max(
                next_arrival_s,
                previous + self.minimum_gap_s,
            )

        self._reserved_arrival[next_stop.platform_id] = next_arrival_s

        scheduler.schedule(
            TrainArrival(
                time_s=next_arrival_s,
                train_id=train.id,
                station_id=next_stop.station_id,
                platform_id=next_stop.platform_id,
                scheduled_s=next_stop.arrival_s,
                disruption_delay_s=0.0,
            )
        )
