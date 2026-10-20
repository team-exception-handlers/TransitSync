# AI contribution: 50% or more AI-generated

import json
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulator.engine.event_log import PASSENGER_EVENT_TYPES
from simulator.engine.event_queue import Scheduler
from simulator.engine.events import (
    Alighting,
    Boarding,
    MissedConnection,
    PassengerArrival,
    TrainDeparture,
)
from simulator.engine.random_streams import StreamManager
from simulator.engine.runner import run_scenario
from simulator.passengers import (
    BoardingComponent,
    CorridorQueue,
    DemandPeriod,
    DemandProfile,
    Passenger,
    PassengerState,
    TransferComponent,
    TransferRoute,
)
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


def passenger(passenger_id, destination="B", state=PassengerState.WALKING):
    return Passenger(passenger_id, "origin", destination, state)


def train(train_id="metro", capacity=3, arrival_s=100, departure_s=120, **kwargs):
    return Train(
        train_id,
        capacity,
        (
            ScheduledStop("A", "P", arrival_s, departure_s),
            ScheduledStop("B", "Q", departure_s + 100, departure_s + 120),
        ),
        **kwargs,
    )


def arrival(passenger_id, time_s, platform="P"):
    return PassengerArrival(
        time_s=time_s, passenger_id=passenger_id, group_id="g", platform_id=platform
    )


def simulate(trains, passengers, events=(), *, initial=None, end_s=150, reverse=False):
    trains = TrainComponent(trains, minimum_gap_s=10)
    boarding = BoardingComponent(trains, passengers, initial_onboard=initial)
    components = [trains, boarding] if not reverse else [boarding, trains]
    scheduler = Scheduler()
    records = []
    for component in components:
        component.start(scheduler)
    for event in events:
        scheduler.schedule(event)

    def handle(event):
        records.append(event)
        for component in components:
            component.handle(event, scheduler)

    scheduler.run_until(end_s, handle)
    return boarding, records


def select(events, cls):
    return [event for event in events if isinstance(event, cls)]


def test_fifo_boarding_updates_identity_manifest_load_and_departure_counts():
    people = {key: passenger(key) for key in ("later", "first", "middle")}
    metro = train(capacity=2)
    boarding, records = simulate(
        [metro],
        people,
        [
            arrival("later", 95),
            arrival("first", 80),
            arrival("middle", 90),
        ],
    )
    assert [e.passenger_id for e in select(records, Boarding)] == ["first", "middle"]
    assert boarding.onboard == {"metro": ("first", "middle")}
    assert boarding.waiting["P"] == ("later",)
    assert people["first"].state is PassengerState.ON_BOARD
    assert people["later"].state is PassengerState.WAITING
    assert metro.onboard_load == 2
    departure = select(records, TrainDeparture)[0]
    assert (
        departure.boarded_count,
        departure.alighted_count,
        departure.onboard_load,
    ) == (2, 0, 2)
    assert [
        (e.passenger_id, e.train_id) for e in select(records, MissedConnection)
    ] == [("later", "metro")]


def test_destination_alighting_frees_capacity_before_boarding():
    people = {
        "off": passenger("off", "A", PassengerState.ON_BOARD),
        "through": passenger("through", "B", PassengerState.ON_BOARD),
        "new": passenger("new"),
    }
    metro = train(capacity=2, onboard_load=2)
    boarding, records = simulate(
        [metro], people, [arrival("new", 90)], initial={"metro": ["off", "through"]}
    )
    moves = [type(e) for e in records if isinstance(e, Alighting | Boarding)]
    assert moves == [Alighting, Boarding]
    assert people["off"].state is PassengerState.COMPLETED
    assert people["through"].state is PassengerState.ON_BOARD
    assert boarding.onboard["metro"] == ("through", "new")
    departure = select(records, TrainDeparture)[0]
    assert (
        departure.boarded_count,
        departure.alighted_count,
        departure.onboard_load,
    ) == (1, 1, 2)


def test_boarded_passenger_completes_at_destination_and_counts_reset_per_stop():
    people = {"p": passenger("p")}
    boarding, records = simulate([train()], people, [arrival("p", 110)], end_s=300)
    assert people["p"].state is PassengerState.COMPLETED
    assert boarding.onboard["metro"] == ()
    assert [(e.time_s, e.platform_id) for e in select(records, Alighting)] == [
        (220, "Q")
    ]
    assert [
        (e.boarded_count, e.alighted_count, e.onboard_load)
        for e in select(records, TrainDeparture)
    ] == [(1, 0, 1), (0, 1, 0)]


@pytest.mark.parametrize(
    "time_s, boards",
    [
        (90, True),
        (100, True),
        (110, True),
        (120, True),
        (120.001, False),
    ],
)
def test_before_during_and_exact_door_closure_boundaries(time_s, boards):
    people = {"p": passenger("p")}
    _, records = simulate([train()], people, [arrival("p", time_s)])
    assert len(select(records, Boarding)) == int(boards)
    assert len(select(records, MissedConnection)) == int(not boards)
    if boards:
        assert people["p"].state is PassengerState.ON_BOARD
    else:
        assert people["p"].state is PassengerState.WAITING
        assert select(records, MissedConnection)[0].train_id == "metro"


def test_late_passenger_misses_first_train_then_boards_the_next():
    people = {"p": passenger("p")}
    boarding, records = simulate(
        [train("first"), train("next", arrival_s=200, departure_s=220)],
        people,
        [arrival("p", 130)],
        end_s=250,
    )
    assert [(e.train_id, e.time_s) for e in select(records, MissedConnection)] == [
        ("first", 130)
    ]
    assert [(e.train_id, e.time_s) for e in select(records, Boarding)] == [
        ("next", 200)
    ]
    assert boarding.onboard["next"] == ("p",)


def test_unserved_destinations_and_other_platforms_stay_waiting():
    people = {"wrong-route": passenger("wrong-route", "Z"), "other": passenger("other")}
    boarding, records = simulate(
        [train()], people, [arrival("wrong-route", 90), arrival("other", 90, "R")]
    )
    assert select(records, Boarding) == []
    assert select(records, MissedConnection) == []
    assert boarding.waiting == {"P": ("wrong-route",), "R": ("other",)}


def test_unserved_queue_head_does_not_block_compatible_passengers():
    people = {"wrong-route": passenger("wrong-route", "Z"), "valid": passenger("valid")}
    _, records = simulate(
        [train(capacity=1)], people, [arrival("wrong-route", 80), arrival("valid", 90)]
    )
    assert [e.passenger_id for e in select(records, Boarding)] == ["valid"]


def test_multiple_open_trains_cannot_board_one_passenger_twice_or_exceed_capacity():
    people = {key: passenger(key) for key in ("p1", "p2", "p3")}
    boarding, records = simulate(
        [
            train("first", capacity=1, departure_s=130),
            train("second", capacity=1, arrival_s=110, departure_s=140),
        ],
        people,
        [arrival("p1", 90), arrival("p2", 90), arrival("p3", 90)],
    )
    assert [(e.passenger_id, e.train_id) for e in select(records, Boarding)] == [
        ("p1", "first"),
        ("p2", "second"),
    ]
    assert boarding.waiting["P"] == ("p3",)
    assert all(t.onboard_load <= t.capacity for t in boarding.trains.trains.values())


def test_doors_stay_open_during_minimum_gap_wait_and_departure_uses_final_counts():
    people = {"p": passenger("p")}
    # First departs at 210; follower cannot leave until 300 with a 90 s gap.
    first = train("first", arrival_s=100, departure_s=210)
    follower = train("follower", arrival_s=190, departure_s=210)
    trains = TrainComponent([first, follower], minimum_gap_s=90)
    boarding = BoardingComponent(trains, people)
    scheduler = Scheduler()
    trains.start(scheduler)
    scheduler.schedule(arrival("p", 250))
    records = []

    def handle(event):
        records.append(event)
        trains.handle(event, scheduler)
        boarding.handle(event, scheduler)

    scheduler.run_until(305, handle)
    departures = select(records, TrainDeparture)
    assert [(e.train_id, e.time_s, e.boarded_count) for e in departures] == [
        ("first", 210, 0),
        ("follower", 300, 1),
    ]
    assert select(records, Boarding)[0].train_id == "follower"


def test_a_train_that_left_before_the_transfer_started_is_not_a_missed_connection():
    people = {"p": passenger("p")}
    external = Alighting(
        time_s=130, passenger_id="p", train_id="feeder", platform_id="rem"
    )
    _, records = simulate([train()], people, [external, arrival("p", 140)])
    assert select(records, MissedConnection) == []


def test_untracked_aggregate_seats_remain_occupied():
    people = {"p": passenger("p")}
    metro = train(capacity=1, onboard_load=1)
    _, records = simulate([metro], people, [arrival("p", 90)])
    assert select(records, Boarding) == []
    assert metro.onboard_load == 1


@settings(max_examples=30)
@given(count=st.integers(0, 12), capacity=st.integers(1, 6))
def test_capacity_fifo_and_passenger_conservation(count, capacity):
    people = {f"p{i}": passenger(f"p{i}") for i in range(count)}
    metro = train(capacity=capacity)
    boarding, records = simulate(
        [metro], people, [arrival(key, 10 + i) for i, key in enumerate(people)]
    )
    expected = tuple(people)[:capacity]
    assert boarding.onboard["metro"] == expected
    assert [e.passenger_id for e in select(records, Boarding)] == list(expected)
    assert metro.onboard_load == min(count, capacity)
    assert len(boarding.onboard["metro"]) + len(boarding.waiting["P"]) == count


@pytest.mark.parametrize("reverse", [False, True])
def test_full_transfer_boarding_alighting_logs_and_filtering_are_reproducible(
    tmp_path, reverse
):
    finished = []

    def build(_scenario, streams):
        feeders = Train("feeder", 800, (ScheduledStop("A", "rem", 10, 30),))
        metro = train(capacity=800, arrival_s=50, departure_s=70)
        trains = TrainComponent([feeders, metro], minimum_gap_s=10)
        transfers = TransferComponent(
            [
                TransferRoute(
                    "A",
                    "rem",
                    "P",
                    DemandProfile((DemandPeriod(0, 10, 60),)),
                    {"B": 1},
                    CorridorQueue(6000),
                    walking_mean_s=2,
                    walking_min_s=1,
                )
            ],
            streams,
        )
        boarding = BoardingComponent(trains, transfers.passengers)
        finished.append(boarding)
        return (
            [boarding, trains, transfers] if reverse else [trains, transfers, boarding]
        )

    scenario = SimpleNamespace(master_seed=42, duration_s=400)
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
    assert finished[0].passengers == finished[2].passengers
    assert len(finished[0].passengers) > 0
    assert all(
        p.state is PassengerState.COMPLETED for p in finished[0].passengers.values()
    )
    records = [json.loads(line) for line in first.events_path.read_text().splitlines()]
    for passenger_id in finished[0].passengers:
        assert [
            r["event_type"] for r in records if r.get("passenger_id") == passenger_id
        ] == [
            "alighting",
            "corridor_arrival",
            "passenger_arrival",
            "boarding",
            "alighting",
        ]
    departures = [
        r
        for r in records
        if r["event_type"] == "train_departure" and r["train_id"] == "metro"
    ]
    count = len(finished[0].passengers)
    feeder_departure = next(
        r
        for r in records
        if r["event_type"] == "train_departure" and r["train_id"] == "feeder"
    )
    assert (feeder_departure["alighted_count"], feeder_departure["onboard_load"]) == (
        count,
        0,
    )
    assert [
        (r["boarded_count"], r["alighted_count"], r["onboard_load"]) for r in departures
    ] == [(count, 0, count), (0, count, 0)]
    assert all(
        "passenger_id" not in json.loads(line)
        for line in filtered.events_path.read_text().splitlines()
    )


@pytest.mark.parametrize(
    "initial, message",
    [
        ({"missing-train": ["p"]}, "unknown train"),
        ({"metro": "p"}, "sequences"),
        ({"metro": ["unknown"]}, "known and unique"),
        ({"metro": [None]}, "strings"),
        ({}, "every ON_BOARD"),
        ([], "map train IDs"),
    ],
)
def test_invalid_initial_manifest_is_rejected(initial, message):
    people = {"p": passenger("p", "A", PassengerState.ON_BOARD)}
    with pytest.raises(ValueError, match=message):
        BoardingComponent(
            TrainComponent([train(onboard_load=1)]), people, initial_onboard=initial
        )


def test_initial_manifest_cannot_exceed_load_duplicate_or_use_wrong_state_or_route():
    trains = TrainComponent([train(onboard_load=1)])
    people = {"p": passenger("p", "A", PassengerState.ON_BOARD)}
    with pytest.raises(ValueError, match="exceeds"):
        BoardingComponent(trains, people, initial_onboard={"metro": ["p", "p"]})
    with pytest.raises(ValueError, match="known and unique"):
        BoardingComponent(
            TrainComponent([train(onboard_load=2)]),
            people,
            initial_onboard={"metro": ["p", "p"]},
        )
    with pytest.raises(ValueError, match="must be ON_BOARD"):
        BoardingComponent(
            trains, {"p": passenger("p")}, initial_onboard={"metro": ["p"]}
        )
    with pytest.raises(ValueError, match="not on the train route"):
        BoardingComponent(
            trains,
            {"p": passenger("p", "Z", PassengerState.ON_BOARD)},
            initial_onboard={"metro": ["p"]},
        )


def test_bad_component_inputs_are_rejected_and_foreign_passenger_events_ignored():
    trains = TrainComponent([train()])
    with pytest.raises(ValueError, match="trains"):
        BoardingComponent(None, {})
    with pytest.raises(ValueError, match="passengers"):
        BoardingComponent(trains, {"wrong": passenger("p")})
    boarding, records = simulate([train()], {}, [arrival("foreign", 90)])
    assert boarding.onboard["metro"] == ()
    assert select(records, Boarding) == []
