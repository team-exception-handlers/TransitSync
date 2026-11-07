# AI contribution: 50% or more AI-generated
"""LLL prototype for #24: compare boarding sequences with a reference queue."""

import pytest
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

from simulator.engine.events import PassengerArrival
from simulator.passengers.platform_queue import PlatformQueue
from simulator.trains.train import ScheduledStop, Train


class CapacityStateMachine(RuleBasedStateMachine):
    """One train and platform; initial riders are separate from generated IDs."""

    @initialize(
        capacity=st.integers(min_value=1, max_value=100),
        occupancy_percent=st.integers(min_value=0, max_value=100),
    )
    def setup(self, capacity, occupancy_percent):
        self.initial_load = capacity * occupancy_percent // 100
        self.expected_load = self.initial_load
        self.train = Train(
            "train",
            capacity,
            (ScheduledStop("station", "P", 0, 1),),
            onboard_load=self.initial_load,
        )
        self.queue = PlatformQueue(("P",))
        self.waiting = []
        self.boarded = []
        self.arrived = []

    @rule()
    def arrive(self):
        passenger_id = f"passenger-{len(self.arrived)}"
        event = PassengerArrival(
            time_s=len(self.arrived),
            passenger_id=passenger_id,
            group_id="group",
            platform_id="P",
        )
        assert self.queue.arrive(event)
        self.arrived.append(passenger_id)
        self.waiting.append(passenger_id)

    @rule()
    def board(self):
        # Derive expected space independently of Train.available_capacity.
        spaces = self.train.capacity - self.expected_load
        expected_ids = self.waiting[:spaces]
        actual_ids = self.queue.board("P", self.train)
        assert actual_ids == expected_ids, "Boarding must match reference FIFO order"
        self.waiting = self.waiting[len(expected_ids) :]
        self.expected_load += len(expected_ids)
        self.boarded.extend(actual_ids)

    @invariant()
    def capacity_and_passengers_are_preserved(self):
        assert 0 <= self.train.onboard_load <= self.train.capacity
        assert self.train.onboard_load == self.expected_load
        assert self.train.onboard_load == self.initial_load + len(self.boarded)
        assert self.queue.waiting_count("P") == len(self.waiting), (
            "Queue lost passengers"
        )
        accounted = self.boarded + self.waiting
        assert len(accounted) == len(set(accounted)), "Passenger counted twice"
        assert accounted == self.arrived, "Passenger conservation or FIFO violated"


TestCapacitySequences = CapacityStateMachine.TestCase
TestCapacitySequences.settings = settings(
    max_examples=100,
    stateful_step_count=50,
    deadline=None,
    derandomize=True,
)


@pytest.mark.parametrize("occupancy_percent", [0, 50, 100])
def test_repeated_boarding_retains_overflow(occupancy_percent):
    """Guarantee empty, partial and full initial trains, plus a later arrival."""
    machine = CapacityStateMachine()
    try:
        machine.setup(capacity=4, occupancy_percent=occupancy_percent)
        for _ in range(6):
            machine.arrive()
        machine.board()
        machine.capacity_and_passengers_are_preserved()
        machine.arrive()
        machine.board()
        machine.board()
        machine.capacity_and_passengers_are_preserved()
    finally:
        machine.teardown()
