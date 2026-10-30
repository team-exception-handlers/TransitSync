# AI contribution: 50% or more AI-generated
"""Pulsed arrivals and chronological corridor integration"""

import json
import math
from types import SimpleNamespace

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulator.engine.event_log import PASSENGER_EVENT_TYPES
from simulator.engine.event_queue import Scheduler
from simulator.engine.events import (
    Alighting,
    Boarding,
    CorridorArrival,
    DepartureDue,
    PassengerArrival,
    TrainArrival,
    TrainDeparture,
)
from simulator.engine.random_streams import StreamManager
from simulator.engine.runner import run_scenario
from simulator.passengers import (
    CorridorQueue,
    DemandPeriod,
    DemandProfile,
    PassengerState,
    TransferComponent,
    TransferRoute,
)
from simulator.passengers.platform_queue import PlatformQueue
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


def route(**overrides):
    values = {
        "station_id": "mcgill",
        "feeder_platform_id": "rem",
        "connecting_platform_id": "green",
        "demand_profile": DemandProfile((DemandPeriod(0, 1000, 60),)),
        "transfer_fractions": {"bonaventure": 1},
        "corridor": CorridorQueue(6000),
        "walking_mean_s": 10,
        "walking_min_s": 0,
    }
    return TransferRoute(**(values | overrides))


def feeder(time_s, **overrides):
    values = {
        "time_s": time_s,
        "scheduled_s": time_s,
        "train_id": f"rem-{time_s}",
        "station_id": "mcgill",
        "platform_id": "rem",
        "disruption_delay_s": 0,
    }
    return TrainArrival(**(values | overrides))


def fixed_component(monkeypatch, walks=(20, 5, 10), routes=None):
    """Fix counts and walks while retaining real demand and destination logic."""
    streams = StreamManager(42)
    get_stream = streams.get_stream
    means = []

    def poisson(mean):
        means.append(mean)
        return len(walks)

    counts = SimpleNamespace(poisson=poisson)
    monkeypatch.setattr(
        streams,
        "get_stream",
        lambda name: counts if name == "group_sizes" else get_stream(name),
    )
    component = TransferComponent([route()] if routes is None else routes, streams)
    monkeypatch.setattr(
        component._walking_sampler, "sample", lambda **kwargs: np.array(walks)
    )
    return component, means


def advance(component, scheduler, end_s):
    events = []

    def handle(event):
        events.append(event)
        component.handle(event, scheduler)

    scheduler.run_until(end_s, handle)
    return events


def arrivals(events):
    return [event for event in events if isinstance(event, PassengerArrival)]


def test_without_feeder_trains_there_are_no_passengers_or_scheduled_events(monkeypatch):
    component, means = fixed_component(monkeypatch)
    scheduler = Scheduler()
    component.start(scheduler)

    assert advance(component, scheduler, 1000) == []
    assert component.passengers == {}
    assert means == []
    assert scheduler.pending == 0


def test_full_group_is_created_at_actual_train_arrival_then_spread_by_walking(
    monkeypatch,
):
    component, means = fixed_component(monkeypatch)
    scheduler = Scheduler()
    scheduler.schedule(feeder(100, scheduled_s=90))

    assert advance(component, scheduler, 99) == []
    assert component.passengers == {}
    at_train = advance(component, scheduler, 100)
    assert means == [100]  # 100 seconds at 60/min, sampled together at arrival.
    assert len(component.passengers) == 3
    assert all(p.state is PassengerState.WALKING for p in component.passengers.values())
    assert [e.time_s for e in at_train if isinstance(e, Alighting)] == [100] * 3

    reached = arrivals(advance(component, scheduler, 200))
    assert [(e.passenger_id, e.time_s) for e in reached] == [
        ("passenger-000000000002", 105),
        ("passenger-000000000003", 110),
        ("passenger-000000000001", 120),
    ]
    assert {e.group_id for e in reached} == {"passenger-group-000001"}
    assert {e.platform_id for e in reached} == {"green"}
    assert all(p.state is PassengerState.WAITING for p in component.passengers.values())


def test_successive_trains_consume_demand_once_across_rate_changes(monkeypatch):
    demand = DemandProfile((DemandPeriod(0, 60, 12), DemandPeriod(60, 120, 30)))
    component, means = fixed_component(
        monkeypatch, walks=(1,), routes=[route(demand_profile=demand)]
    )
    scheduler = Scheduler()
    for time_s in (30, 90, 120):
        scheduler.schedule(feeder(time_s))
    reached = arrivals(advance(component, scheduler, 200))

    # Each train collects demand since the previous arrival (or simulation start).
    # First train: 0-30 s at 12 passengers/minute gives 6 expected passengers.
    # Second: 30-60 s at 12/min gives 6, then 60-90 s at 30/min gives 15: total 21.
    # Third: 90-120 s at 30/min gives 15. Total expected demand across trains: 42.
    assert means == [6, 21, 15]
    assert [e.time_s for e in reached] == [31, 91, 121]
    assert len({e.group_id for e in reached}) == 3
    assert len({e.passenger_id for e in reached}) == 3


@pytest.mark.parametrize(
    "overrides", [{"station_id": "other"}, {"platform_id": "green"}]
)
def test_unconfigured_feeder_arrivals_are_ignored(monkeypatch, overrides):
    component, means = fixed_component(monkeypatch)
    scheduler = Scheduler()
    scheduler.schedule(feeder(100, **overrides))

    assert len(advance(component, scheduler, 500)) == 1
    assert component.passengers == {}
    assert means == []


def test_zero_demand_does_not_spend_ids_or_create_a_walk(monkeypatch):
    demand = DemandProfile((DemandPeriod(60, 120, 60),))
    component, means = fixed_component(
        monkeypatch, walks=(1,), routes=[route(demand_profile=demand)]
    )
    scheduler = Scheduler()
    scheduler.schedule(feeder(60))
    scheduler.schedule(feeder(120))
    assert arrivals(advance(component, scheduler, 60)) == []
    assert means == []
    assert scheduler.pending == 1  # Only the next feeder, no passenger timer.
    reached = arrivals(advance(component, scheduler, 200))
    assert means == [60]
    assert reached[0].passenger_id == "passenger-000000000001"
    assert reached[0].group_id == "passenger-group-000001"


def test_overlapping_groups_enter_corridor_in_physical_arrival_order(monkeypatch):
    component, _ = fixed_component(monkeypatch, walks=(100, 110))
    walks = iter((np.array([100, 110]), np.array([1, 2])))
    monkeypatch.setattr(
        component._walking_sampler, "sample", lambda **kwargs: next(walks)
    )
    scheduler = Scheduler()
    scheduler.schedule(feeder(10))
    scheduler.schedule(feeder(20))
    reached = arrivals(advance(component, scheduler, 200))

    # The second train's walkers reach the queue before the first train's walkers.
    assert [(e.passenger_id, e.time_s) for e in reached] == [
        ("passenger-000000000003", 21),
        ("passenger-000000000004", 22),
        ("passenger-000000000001", 110),
        ("passenger-000000000002", 120),
    ]


def test_corridor_capacity_adds_queue_delay_after_walking(monkeypatch):
    component, _ = fixed_component(
        monkeypatch, walks=(5, 5, 5), routes=[route(corridor=CorridorQueue(30))]
    )
    scheduler = Scheduler()
    scheduler.schedule(feeder(10))
    reached = arrivals(advance(component, scheduler, 100))

    # All reach the queue at 15; 30/min means one passage every 2 seconds.
    assert [e.time_s for e in reached] == [15, 17, 19]
    assert [p.queue_delay_s for p in component.passages.values()] == [0, 2, 4]


def test_zero_walk_completes_before_departure_decision_at_same_instant(monkeypatch):
    component, _ = fixed_component(monkeypatch, walks=(0,))
    scheduler = Scheduler()
    scheduler.schedule(feeder(100))
    scheduler.schedule(
        DepartureDue(
            time_s=100,
            scheduled_s=100,
            train_id="green-1",
            station_id="mcgill",
            platform_id="green",
        )
    )
    assert [type(e) for e in advance(component, scheduler, 100)] == [
        TrainArrival,
        Alighting,
        CorridorArrival,
        PassengerArrival,
        DepartureDue,
    ]


def test_shared_corridor_and_independent_demand_for_two_feeder_routes(monkeypatch):
    corridor = CorridorQueue(30)
    routes = [
        route(corridor=corridor),
        route(
            corridor=corridor, feeder_platform_id="blue", connecting_platform_id="rem"
        ),
    ]
    component, means = fixed_component(monkeypatch, walks=(5,), routes=routes)
    scheduler = Scheduler()
    scheduler.schedule(feeder(100))
    scheduler.schedule(feeder(100, train_id="blue-1", platform_id="blue"))
    reached = arrivals(advance(component, scheduler, 200))

    assert means == [100, 100]
    assert [(e.platform_id, e.time_s) for e in reached] == [
        ("green", 105),
        ("rem", 107),
    ]


def test_transfer_arrivals_form_train_linked_pulses_never_a_continuous_rate(
    monkeypatch,
):
    component, _ = fixed_component(monkeypatch, walks=(5, 6, 10))
    scheduler = Scheduler()
    scheduler.schedule(feeder(100))
    scheduler.schedule(feeder(400))
    reached = arrivals(advance(component, scheduler, 600))

    # A constant-rate model would fill the 295-second quiet gap or emit before 100.
    assert [e.time_s for e in reached] == [105, 106, 110, 405, 406, 410]
    assert [e.group_id for e in reached[:3]] == ["passenger-group-000001"] * 3
    assert [e.group_id for e in reached[3:]] == ["passenger-group-000002"] * 3


@settings(max_examples=20)
@given(shift=st.integers(min_value=0, max_value=500))
def test_delaying_a_feeder_shifts_its_entire_pulse(shift):
    def pulse(time_s):
        component = TransferComponent([route()], StreamManager(42))
        passengers = component._generator.generate(
            origin="mcgill",
            demand_profile=route().demand_profile,
            start_s=0,
            end_s=5,
            transfer_fractions={"bonaventure": 1},
        )
        component._generator.generate = lambda **kwargs: passengers
        component._walking_sampler.sample = lambda **kwargs: (
            np.arange(len(passengers)) + 5
        )
        scheduler = Scheduler()
        scheduler.schedule(feeder(time_s))
        return [e.time_s for e in arrivals(advance(component, scheduler, 1000))]

    original = pulse(100)
    assert len(original) > 1
    assert pulse(100 + shift) == [time_s + shift for time_s in original]


def test_real_train_walks_and_filtered_logs_are_reproducible(tmp_path):
    components = []

    def build(_scenario, streams):
        train = Train(
            "rem-1",
            800,
            (ScheduledStop("mcgill", "rem", 100, 130),),
            current_delay=20,
            generated_delay_s=20,
        )
        transfers = TransferComponent([route(walking_min_s=5)], streams)
        components.append(transfers)
        return [TrainComponent([train]), transfers]

    scenario = SimpleNamespace(master_seed=42, duration_s=600)
    first = run_scenario(scenario, StreamManager, build, tmp_path / "first")
    second = run_scenario(scenario, StreamManager, build, tmp_path / "second")
    filtered = run_scenario(
        scenario,
        StreamManager,
        build,
        tmp_path / "filtered",
        skip_event_types=PASSENGER_EVENT_TYPES,
    )
    assert first.events_path.read_bytes() == second.events_path.read_bytes()
    assert first.summary_path.read_bytes() == second.summary_path.read_bytes()
    assert len(components[0].passengers) > 0
    assert components[0].passengers == components[2].passengers
    assert all(
        p.state is PassengerState.WAITING for p in components[0].passengers.values()
    )
    records = [json.loads(line) for line in first.events_path.read_text().splitlines()]
    assert records[0]["event_type"] == "train_arrival"
    assert records[0]["time_s"] == 120
    reached = [r for r in records if r["event_type"] == "passenger_arrival"]
    assert min(r["time_s"] for r in reached) >= 125
    assert len({r["time_s"] for r in reached}) > 1
    assert all(
        "passenger_id" not in json.loads(line)
        for line in filtered.events_path.read_text().splitlines()
    )


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"station_id": " "}, "station_id"),
        ({"feeder_platform_id": None}, "feeder_platform_id"),
        ({"connecting_platform_id": " rem "}, "connecting_platform_id"),
        ({"demand_profile": None}, "demand_profile"),
        ({"transfer_fractions": {"bonaventure": 0.5}}, "transfer_fractions"),
        ({"corridor": None}, "corridor"),
        ({"walking_mean_s": math.nan}, "walking_mean_s"),
        ({"walking_min_s": -1}, "walking_min_s"),
        ({"walking_mean_s": 0}, "walking_mean_s"),
        ({"demand_start_s": True}, "demand_start_s"),
    ],
)
def test_invalid_route_configuration_is_rejected(overrides, field):
    with pytest.raises(ValueError, match=field):
        route(**overrides)


def test_route_snapshots_fractions_and_rejects_duplicate_sources():
    fractions = {"bonaventure": 1}
    configured = route(transfer_fractions=fractions)
    fractions["bonaventure"] = 0
    assert configured.transfer_fractions == {"bonaventure": 1}
    with pytest.raises(ValueError, match="unique"):
        TransferComponent([configured, configured], StreamManager(42))


def test_demand_start_and_unknown_passenger_events(monkeypatch):
    component, means = fixed_component(
        monkeypatch, walks=(1,), routes=[route(demand_start_s=60)]
    )
    scheduler = Scheduler()
    scheduler.schedule(feeder(30))
    scheduler.schedule(feeder(60))
    scheduler.schedule(feeder(90))
    scheduler.schedule(
        CorridorArrival(
            time_s=50, passenger_id="foreign", group_id="other", platform_id="green"
        )
    )
    scheduler.schedule(
        PassengerArrival(
            time_s=50, passenger_id="foreign", group_id="other", platform_id="green"
        )
    )
    reached = arrivals(advance(component, scheduler, 200))
    assert means == [30]
    assert reached[-1].time_s == 91
    assert list(component.passengers) == ["passenger-000000000001"]


@pytest.mark.parametrize("invalid", [None, "route", [object()]])
def test_component_requires_a_sequence_of_routes(invalid):
    with pytest.raises(ValueError, match="routes"):
        TransferComponent(invalid, StreamManager(42))


def test_route_normalizes_ids_before_matching_arrivals(monkeypatch):
    configured = route(
        station_id=" mcgill ",
        feeder_platform_id=" rem ",
        connecting_platform_id=" green ",
    )
    component, means = fixed_component(monkeypatch, walks=(5,), routes=[configured])
    scheduler = Scheduler()
    scheduler.schedule(feeder(100))
    reached = arrivals(advance(component, scheduler, 200))
    assert means == [100]
    assert reached[0].platform_id == "green"
    assert next(iter(component.passengers.values())).origin == "mcgill"
    with pytest.raises(ValueError, match="unique"):
        TransferComponent([configured, route()], StreamManager(42))


@pytest.mark.parametrize("transfers_first", [False, True])
def test_real_platform_queue_boards_pulse_and_retains_overflow(
    monkeypatch, tmp_path, transfers_first
):
    transfers, means = fixed_component(monkeypatch)
    queue = PlatformQueue(("green",))
    feeder_train = Train("rem-1", 800, (ScheduledStop("mcgill", "rem", 100, 130),))
    connecting = Train("green-1", 2, (ScheduledStop("mcgill", "green", 100, 110),))
    trains = TrainComponent([feeder_train, connecting], passenger_queue=queue)
    components = [transfers, trains] if transfers_first else [trains, transfers]
    result = run_scenario(
        SimpleNamespace(master_seed=42, duration_s=200),
        StreamManager,
        lambda scenario, streams: components,
        tmp_path / "run",
    )
    records = [json.loads(line) for line in result.events_path.read_text().splitlines()]
    boarded = [r for r in records if r["event_type"] == Boarding.event_type]
    departure = next(
        r
        for r in records
        if r["event_type"] == TrainDeparture.event_type and r["train_id"] == "green-1"
    )
    # Walks 5 and 10 reach the train by departure at 110; the 20-second walk misses it.
    assert means == [100]
    assert [r["time_s"] for r in boarded] == [105, 110]
    assert (departure["boarded_count"], departure["onboard_load"]) == (2, 2)
    assert queue.waiting_count("green") == 1
    assert [p.state for p in transfers.passengers.values()] == [
        PassengerState.WAITING,
        PassengerState.ON_BOARD,
        PassengerState.ON_BOARD,
    ]
