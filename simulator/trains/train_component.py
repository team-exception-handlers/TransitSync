"""Connect generated trains to the deterministic event engine."""

from collections.abc import Sequence

from simulator.engine.event_queue import Scheduler
from simulator.engine.events import Event, TrainArrival
from simulator.trains.train import Train
class TrainComponent:
    """Owns train objects for the entire simulation run."""

    def __init__(self, trains:Sequence[Train]) -> None:
        self.trains = {}

        for train in trains:
            if train.id in self.trains:
                raise ValueError(f"Duplicate train ID: {train.id}")

            self.trains[train.id] = train

    def start(self, scheduler: Scheduler) -> None:
        """Schedule the first arrival of each train"""

        for train in self.trains.values():
            first_stop = train.schedule[0]

            scheduler.schedule(TrainArrival(time_s = first_stop.arrival_s, train_id = train.id, station_id = first_stop.station_id, platform_id = first_stop.platform_id,scheduled_s = first_stop.arrival_s, disruption_delay_s = 0.0))

    def handle(self, event: Event, scheduler: Scheduler) -> None:
        """Need to implement train movement and dwell handling"""
        pass

    