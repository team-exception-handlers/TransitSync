import pytest

from simulator.trains.train import Train, ScheduledStop
from simulator.trains.train_generator import (generate_from_schedule, generate_from_headway,)

@pytest.fixture
def route():
    return [
        ScheduledStop("A", "P1", 0, 0),
        ScheduledStop("B", "P2", 280, 300),
        ScheduledStop("C", "P3", 580, 600),
        ]

def test_generate_from_schedule(route):
    trains = generate_from_schedule(departure_times_s = [0, 600, 1200], route = route, capacity = 800, line_id = "green",)

    assert len(trains) == 3
    assert [train.id for train in trains] == [
        "green_0001",
        "green_0002",
        "green_0003",
    ]
    assert trains[1].schedule[0].departure_s == 600

def test_generate_from_headway(route):
    trains = generate_from_headway(start_s = 0, end_s = 1200, headway_s = 300, route = route, capacity = 800, line_id = "green",)

    assert len(trains) == 5
    assert [t.schedule[0].departure_s for t in trains] == [0, 300, 600, 900, 1200]

def test_train_identity_persists(route):
    train = Train(id = "green_0001", capacity = 800, schedule = tuple(route),)

    original_id = train.id

    assert train.advance_stop()
    assert train.id == original_id

def test_capacity_constraint(route):
    train = Train(id="green_0001", capacity = 100, schedule = tuple(route),)

    train.board(80)
    assert train.onboard_load == 80

    with pytest.raises(ValueError):
        train.board(30)

    train.alight(20)
    assert train.onboard_load == 60

def test_deterministic_generation(route):
    def generate():
        return generate_from_headway(start_s = 0, end_s = 1200, headway_s = 300, route = route, capacity = 800, line_id = "green",)
    assert generate() == generate()

def test_invalid_headway(route):
    with pytest.raises(ValueError):
        generate_from_headway(start_s = 0, end_s = 1200, headway_s = 0, route = route, capacity = 800, line_id = "green",)