# AI contribution: 50% or more AI-generated
"""All three features together through the runner and versioned event log."""

import json

from simulator.engine.events import PassengerArrival, event_from_record
from simulator.engine.random_streams import StreamManager
from simulator.engine.runner import run_scenario
from simulator.passengers.platform_queue import PlatformQueue
from simulator.trains.suspension import LineSuspension
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent
from simulator.trains.train_generator import generate_from_headway


class PassengerBurst:
    def start(self, scheduler):
        for index in range(7):
            scheduler.schedule(
                PassengerArrival(
                    time_s=10 + index,
                    passenger_id=f"p{index}",
                    group_id="burst",
                    platform_id="P",
                )
            )

    def handle(self, event, scheduler):
        pass


def build_components(scenario, streams):
    route = (ScheduledStop("A", "P", 0, 0), ScheduledStop("B", "Q", 100, 100))
    trains = generate_from_headway(
        50,
        450,
        100,
        route,
        2,
        "green",
        irregularity_level=0.3,
        rng=streams.get_stream("disruptions"),
    )
    original = trains[0]
    trains[0] = Train(
        original.id,
        2,
        original.schedule,
        line_id="green",
        layover_slack=60,
        return_trips=(
            (
                ScheduledStop("B", "Q-return", 250, 250),
                ScheduledStop("A", "P-return", 350, 350),
            ),
        ),
    )
    component = TrainComponent(
        trains,
        minimum_gap_s=30,
        suspensions=[LineSuspension("green", 50, 200)],
        passenger_queue=PlatformQueue(("P",)),
    )
    return [component, PassengerBurst()]


def test_combined_perturbations_are_byte_reproducible_and_affect_outcomes(
    tmp_path, minimal_scenario
):
    first = run_scenario(
        minimal_scenario, StreamManager, build_components, tmp_path / "one"
    )
    second = run_scenario(
        minimal_scenario, StreamManager, build_components, tmp_path / "two"
    )
    assert first.events_path.read_bytes() == second.events_path.read_bytes()
    assert first.summary_path.read_bytes() == second.summary_path.read_bytes()
    records = [json.loads(line) for line in first.events_path.read_text().splitlines()]
    assert all(event_from_record(record).to_record() == record for record in records)
    departures = [r for r in records if r["event_type"] == "train_departure"]
    origin = [r for r in departures if r["platform_id"] == "P"]
    assert origin[0]["time_s"] == 200
    assert sum(r["boarded_count"] for r in origin) == 7
    assert all(r["onboard_load"] <= 2 for r in departures)
    returned = next(r for r in departures if r["platform_id"] == "Q-return")
    assert returned["train_id"] == "green_0001"
    assert returned["time_s"] == 340  # 150 s late, less 60 s slack, schedule 250
    assert returned["disruption_delay_s"] == 90
    assert all(
        b["time_s"] - a["time_s"] >= 30
        for a, b in zip(origin, origin[1:], strict=False)
    )
