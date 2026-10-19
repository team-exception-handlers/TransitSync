from simulator.engine.event_queue import Scheduler
from simulator.engine.events import TrainArrival
from simulator.trains.train import Train, ScheduledStop
from simulator.trains.train_component import TrainComponent

def test_initial_arrivals_respect_minimum_gap():
    trains = [
        Train(
            id = "train_1",
            capacity = 800,
            schedule = (
                ScheduledStop("A", "P1", 100, 120),
                ),
        ),
        Train(
            id = "train_2",
            capacity = 800,
            schedule = (
                ScheduledStop("A", "P1", 120, 140),
            ),
        ),
        Train(
            id = "train_3",
            capacity = 800,
            schedule = (
                ScheduledStop("A", "P1", 140, 160),
            ),
        ),
    ]

    scheduler = Scheduler()
    component = TrainComponent(trains, minimum_gap_s = 90)

    component.start(scheduler)

    arrivals = []

    def handle(event):
        if isinstance(event, TrainArrival):
            arrivals.append(event)

        component.handle(event, scheduler)
    scheduler.run_until(500, handle)

    assert [event.time_s for event in arrivals] == [100.0, 190.0, 280.0,]
    assert [event.train_id for event in arrivals] == ["train_1", "train_2", "train_3"]