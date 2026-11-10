# AI contribution: 50% or more AI-generated
"""Review regressions for missed-transfer counts and boarding work (#100).

A passenger represents one transfer in the current journey model. Repeated
full departures must not multiply that passenger's missed-connection result.
Lookup counts check boarding work without relying on machine-dependent timing.
The real scheduler verifies that a missed passenger can still complete a trip.
"""

import pytest

from simulator.engine.event_queue import Scheduler
from simulator.engine.events import Boarding, MissedConnection, PassengerArrival
from simulator.passengers import Passenger, PassengerState
from simulator.passengers.platform_queue import PlatformQueue
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


class LookupCounter(dict):
    """Record passenger reads while retaining the shared registry's behavior.

    Reset reads immediately before boarding, excluding arrival bookkeeping.
    State updates also read snapshots, so assertions inspect IDs rather than
    assuming each boarded passenger needs exactly one dictionary access.
    """

    def __init__(self, passengers):
        super().__init__(passengers)
        self.reads = []

    def __getitem__(self, key):
        self.reads.append(key)
        return super().__getitem__(key)


def train_at(train_id, arrival_s=100, departure_s=120, *, capacity=2, load=0):
    """Build an A-to-B train, with times in simulation seconds.

    Aggregate initial loads fill seats without requiring tracked identities.
    Consecutive vehicles have distinct IDs but share the connecting platform P.
    """
    return Train(
        train_id,
        capacity,
        (
            ScheduledStop("A", "P", arrival_s, departure_s),
            ScheduledStop("B", "Q", departure_s + 100, departure_s + 120),
        ),
        onboard_load=load,
    )


def enqueue(queue, passenger_id, time_s=90):
    """Accept one unique passenger at P and return the input arrival event."""
    event = PassengerArrival(
        time_s=time_s, passenger_id=passenger_id, group_id="g", platform_id="P"
    )
    assert queue.arrive(event) is True
    return event


@pytest.mark.parametrize("arrival_s, miss_s", [(90, 120), (130, 130), (175, 175)])
def test_one_miss_per_transfer_across_three_full_trains(arrival_s, miss_s):
    """Waiting, late and mixed cases each produce one miss, then recover.

    Full departures are at 120, 140 and 160 seconds. The 200 arrival has space;
    boarding there must remain possible after the first missed connection.
    The passenger finally alights at B at 320, conserving their identity.
    """
    people = {"p": Passenger("p", "origin", "B")}
    queue = PlatformQueue(("P", "Q"), passengers=people)
    trains = TrainComponent(
        [
            train_at("first", capacity=1, load=1),
            train_at("second", 130, 140, capacity=1, load=1),
            train_at("third", 150, 160, capacity=1, load=1),
            train_at("recovery", 200, 220),
        ],
        minimum_gap_s=10,
        passenger_queue=queue,
    )
    scheduler, records = Scheduler(), []
    trains.start(scheduler)
    scheduler.schedule(
        PassengerArrival(
            time_s=arrival_s, passenger_id="p", group_id="g", platform_id="P"
        )
    )

    def process(event):
        records.append(event)
        trains.handle(event, scheduler)

    scheduler.run_until(350, process)
    assert [
        (e.passenger_id, e.train_id, e.time_s)
        for e in records
        if isinstance(e, MissedConnection)
    ] == [("p", "first", miss_s)]
    assert [(e.train_id, e.time_s) for e in records if isinstance(e, Boarding)] == [
        ("recovery", 200)
    ]
    assert people["p"].state is PassengerState.COMPLETED
    assert queue.waiting_count("P") == 0


def test_full_train_does_not_read_waiting_passengers():
    """A full held train needs no destination checks as more walkers arrive.

    One thousand arrivals formerly triggered 1 + ... + 1000 queue lookups.
    The next empty train must still receive all those passengers in FIFO order.
    """
    ids = [f"p{i}" for i in range(1000)]
    people = LookupCounter({pid: Passenger(pid, "origin", "B") for pid in ids})
    queue = PlatformQueue(("P",), passengers=people)
    full = train_at("full", capacity=1, load=1)
    recovery = train_at("recovery", capacity=len(ids))
    queue.bind_trains({"full": full, "recovery": recovery})
    for pid in ids:
        enqueue(queue, pid)
        people.reads.clear()
        assert queue.board("P", full) == []
        assert people.reads == []
    assert full.onboard_load == 1
    assert queue.waiting_count("P") == len(ids)
    assert queue.board("P", recovery) == ids


def test_boarding_stops_at_capacity_and_preserves_skipped_and_unread_order():
    """Skipped destinations stay ahead of the untouched tail when seats fill.

    The B train boards b0 and b1; it must never inspect tail_z or b2. A later
    Z service boards z0, z1, tail_z in order, and another B service boards b2.
    No passenger is lost while joining skipped entries to the unread queue.
    """
    destinations = {
        "z0": "Z",
        "b0": "B",
        "z1": "Z",
        "b1": "B",
        "tail_z": "Z",
        "b2": "B",
    }
    people = LookupCounter(
        {
            pid: Passenger(pid, "origin", destination)
            for pid, destination in destinations.items()
        }
    )
    queue = PlatformQueue(("P",), passengers=people)
    first, last = train_at("first"), train_at("last")
    other = Train(
        "other",
        3,
        (ScheduledStop("A", "P", 200, 220), ScheduledStop("Z", "Z", 320, 340)),
    )
    queue.bind_trains({train.id: train for train in (first, other, last)})
    for pid in destinations:
        enqueue(queue, pid)
    people.reads.clear()
    assert queue.board("P", first) == ["b0", "b1"]
    assert "tail_z" not in people.reads
    assert "b2" not in people.reads
    assert first.onboard_load == 2
    assert queue.waiting_count("P") == 4
    assert queue.board("P", other) == ["z0", "z1", "tail_z"]
    assert queue.board("P", last) == ["b2"]
    assert queue.waiting_count("P") == 0
