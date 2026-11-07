# AI contribution: 50% or more AI-generated
"""REM scheduled-window budgets, recovery, and holds through the real scheduler."""

import json
from types import SimpleNamespace

import pytest

from simulator.control.decision import DecisionPipeline
from simulator.control.strategies.headway_regulation import HeadwayRegulationStrategy
from simulator.engine.event_queue import Scheduler
from simulator.engine.events import Boarding, PassengerArrival, TrainDeparture
from simulator.engine.runner import run_scenario
from simulator.passengers import Passenger, PassengerState
from simulator.passengers.platform_queue import PlatformQueue
from simulator.trains.door_throughput import DoorThroughput
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


def service(train_id, start, capacity=20, destination="B"):
    """Create a two-stop service with ten seconds of scheduled dwell."""
    return Train(
        train_id,
        capacity,
        (
            ScheduledStop("A", "P", start, start + 10),
            ScheduledStop(destination, destination, start + 100, start + 110),
        ),
    )


def run_boarding(*, capacity=20, rate=0.2, hold=False, arrivals=None):
    """Use repeated arrivals, a different destination, and a recovery train."""
    people = {f"p{i}": Passenger(f"p{i}", "origin", "B") for i in range(6)}
    people["other"] = Passenger("other", "origin", "C")
    queue = PlatformQueue(("P", "B"), passengers=people)
    trains = [service("rem", 100, capacity), service("next", 150)]
    policy = None
    if hold:
        trains.insert(0, service("leader", 50))
        policy = DecisionPipeline(HeadwayRegulationStrategy({"P": 80, "B": 80}))
    component = TrainComponent(
        trains,
        minimum_gap_s=1,
        passenger_queue=queue,
        decision=policy,
        rem_door_throughput={"rem": DoorThroughput(rate, 1)},
    )
    scheduler, records = Scheduler(), []
    component.start(scheduler)
    default_arrivals = [
        ("other", 95),
        ("p0", 96),
        ("p1", 100),
        ("p2", 105),
        ("p3", 110),
        ("p4", 120),
        ("p5", 140),
    ]
    for pid, time_s in default_arrivals if arrivals is None else arrivals:
        scheduler.schedule(
            PassengerArrival(
                time_s=time_s,
                passenger_id=pid,
                group_id="g",
                platform_id="P",
            )
        )

    def process(event):
        records.append(event)
        component.handle(event, scheduler)

    scheduler.run_until(180, process)
    return people, queue, records


@pytest.mark.parametrize("hold", [False, True])
def test_budget_is_cumulative_and_overflow_recovers(hold):
    """0.2 passengers/s * 10 seconds * 1 door = 2 across the entire stop.

    A hold extends closure from 110 to 140, but not the scheduled-dwell budget.
    Repeated arrivals cannot reset that budget; the next train preserves FIFO.
    """
    people, queue, records = run_boarding(hold=hold)
    boardings = [e for e in records if isinstance(e, Boarding)]
    assert [e.passenger_id for e in boardings if e.train_id == "rem"] == ["p0", "p1"]
    assert [e.passenger_id for e in boardings if e.train_id == "next"] == [
        "p2",
        "p3",
        "p4",
        "p5",
    ]
    departure = next(
        e for e in records if isinstance(e, TrainDeparture) and e.train_id == "rem"
    )
    assert departure.time_s == (140 if hold else 110)
    assert departure.boarded_count == 2
    assert departure.onboard_load == 2
    assert queue.waiting_count("P") == 1
    assert people["other"].state is PassengerState.WAITING
    assert all(people[f"p{i}"].state is PassengerState.ON_BOARD for i in range(6))


def test_vehicle_space_remains_a_second_limit():
    """A large door budget cannot override a one-passenger vehicle capacity."""
    _, _, records = run_boarding(capacity=1, rate=20)
    assert [
        e.passenger_id
        for e in records
        if isinstance(e, Boarding) and e.train_id == "rem"
    ] == ["p0"]


@pytest.mark.parametrize(
    "rate,doors,dwell,expected", [(0.3, 1, 10, 3), (0.15, 2, 5, 1), (1, 2, 0, 0)]
)
def test_whole_passenger_rounding(rate, doors, dwell, expected):
    assert DoorThroughput(rate, doors).budget(dwell) == expected


@pytest.mark.parametrize(
    "rate", [True, 0, -1, float("nan"), float("inf"), "1", None, 10**400]
)
def test_invalid_rate(rate):
    with pytest.raises(ValueError, match="passengers_per_second_per_door"):
        DoorThroughput(rate, 1)


@pytest.mark.parametrize("doors", [True, 0, -1, 1.5, "2", None])
def test_invalid_doors(doors):
    with pytest.raises(ValueError, match="doors"):
        DoorThroughput(1, doors)


@pytest.mark.parametrize(
    "dwell", [True, -1, float("nan"), float("inf"), "1", None, 10**400]
)
def test_invalid_dwell(dwell):
    config = DoorThroughput(1, 1)
    with pytest.raises(ValueError, match="scheduled_dwell_s"):
        config.budget(dwell)


@pytest.mark.parametrize("config", [[], {"unknown": DoorThroughput(1, 1)}, {"rem": 1}])
def test_invalid_train_configuration(config):
    trains = [service("rem", 100)]
    with pytest.raises(ValueError, match="rem_door_throughput"):
        TrainComponent(trains, rem_door_throughput=config)


def test_repeated_runs_have_identical_events():
    first = run_boarding()[2]
    second = run_boarding()[2]
    assert first == second


def test_unused_budget_is_available_during_hold_and_at_closure():
    """Two late arrivals consume the fixed budget; one after closure waits."""
    _, _, records = run_boarding(
        hold=True, arrivals=[("p0", 120), ("p1", 140), ("p2", 140.001)]
    )
    assert [
        (e.passenger_id, e.time_s)
        for e in records
        if isinstance(e, Boarding) and e.train_id == "rem"
    ] == [("p0", 120), ("p1", 140)]


def test_invalid_queue_budget_preserves_waiting_passenger():
    """Validate the bound before removing any passenger from the queue."""
    queue = PlatformQueue(("P",))
    queue.arrive(
        PassengerArrival(time_s=0, passenger_id="p", group_id="g", platform_id="P")
    )
    train = service("t", 100)
    with pytest.raises(ValueError, match="max_boarding"):
        queue.board("P", train, max_boarding=-1)
    assert queue.waiting_count("P") == 1
    assert train.onboard_load == 0


def test_each_stop_of_same_train_has_a_fresh_budget():
    """Two ten-second stops each board one passenger using the same train ID."""
    people = {
        "first": Passenger("first", "origin", "C"),
        "second": Passenger("second", "origin", "C"),
    }
    queue = PlatformQueue(("P", "Q", "R"), passengers=people)
    train = Train(
        "rem",
        20,
        (
            ScheduledStop("A", "P", 100, 110),
            ScheduledStop("B", "Q", 200, 210),
            ScheduledStop("C", "R", 300, 310),
        ),
    )
    component = TrainComponent(
        [train],
        passenger_queue=queue,
        rem_door_throughput={"rem": DoorThroughput(0.1, 1)},
    )
    scheduler, boarded = Scheduler(), []
    component.start(scheduler)
    for pid, platform in (("first", "P"), ("second", "Q")):
        scheduler.schedule(
            PassengerArrival(
                time_s=90, passenger_id=pid, group_id="g", platform_id=platform
            )
        )

    def process(event):
        if isinstance(event, Boarding):
            boarded.append((event.passenger_id, event.time_s))
        component.handle(event, scheduler)

    scheduler.run_until(220, process)
    assert boarded == [("first", 100), ("second", 200)]
    assert train.onboard_load == 2


def test_manifest_records_explicit_door_parameters(tmp_path):
    """Two runs preserve settings and emit byte-identical event logs."""
    scenario = SimpleNamespace(duration_s=230, master_seed=42, name="door-budget")

    def build_components(scenario, streams):
        return [
            TrainComponent(
                [service("rem", 100)],
                rem_door_throughput={"rem": DoorThroughput(0.3, 2)},
            )
        ]

    for folder in ("first", "second"):
        run_scenario(scenario, lambda seed: None, build_components, tmp_path / folder)
    manifest = json.loads((tmp_path / "first" / "manifest.json").read_text())
    assert manifest["rem_door_throughput"] == [
        {
            "train_id": "rem",
            "passengers_per_second_per_door": 0.3,
            "doors": 2,
            "window": "scheduled_dwell",
            "rounding": "floor",
        }
    ]
    first = (tmp_path / "first" / "events.jsonl").read_bytes()
    second = (tmp_path / "second" / "events.jsonl").read_bytes()
    assert first == second
