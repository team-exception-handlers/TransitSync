# AI contribution: 50% or more AI-generated
"""Extend the #24 LLL prototype to tracked journeys and successive trains.

The independent model retains incompatible destinations and capacity overflow.
Generated trains alternate freely between routes; waiting IDs must survive until
a compatible train with space arrives. No private production queue is inspected.
"""

from itertools import product

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

from simulator.engine.events import PassengerArrival
from simulator.passengers import Passenger, PassengerState
from simulator.passengers.platform_queue import PlatformQueue
from simulator.trains.train import ScheduledStop, Train


class CapacityJourneyMachine(RuleBasedStateMachine):
    """Reference FIFO model adapted from the single-train learning spike."""

    @initialize()
    def setup(self):
        """Bind a finite fleet before tracked passengers enter the platform.

        Empty, half-full and full trains share capacity with anonymous initial
        riders. The reference loads never depend on production capacity helpers.
        """
        self.people = {}
        self.queue = PlatformQueue(("P",), passengers=self.people)
        self.waiting = []
        self.boarded = []
        self.vehicles = {}
        self.expected_loads = {}
        # Bind through the public interface before any tracked passenger boards.
        for destination, capacity, occupancy in product(
            ("B", "C"), range(1, 11), (0, 50, 100)
        ):
            train_id = f"{destination}-{capacity}-{occupancy}"
            load = capacity * occupancy // 100
            self.vehicles[train_id] = Train(
                train_id,
                capacity,
                (
                    ScheduledStop("A", "P", 0, 10),
                    ScheduledStop(destination, destination, 20, 30),
                ),
                onboard_load=load,
            )
            self.expected_loads[train_id] = load
        self.queue.bind_trains(self.vehicles)

    @rule(destination=st.sampled_from(["B", "C"]))
    def arrive(self, destination):
        """Generate a unique tracked arrival for either connecting route."""
        passenger_id = f"p{len(self.people)}"
        self.people[passenger_id] = Passenger(passenger_id, "origin", destination)
        assert self.queue.arrive(
            PassengerArrival(
                time_s=len(self.people),
                passenger_id=passenger_id,
                group_id="g",
                platform_id="P",
            )
        )
        self.waiting.append(passenger_id)

    @rule(
        destination=st.sampled_from(["B", "C"]),
        capacity=st.integers(min_value=1, max_value=10),
        occupancy_percent=st.sampled_from([0, 50, 100]),
    )
    def serve(self, destination, capacity, occupancy_percent):
        """Compare a service attempt with the compatible reference FIFO prefix.

        Previously skipped IDs retain their positions for a later compatible
        service. Reusing a full train also exercises repeated boarding attempts.
        """
        train_id = f"{destination}-{capacity}-{occupancy_percent}"
        train = self.vehicles[train_id]
        initial_load = self.expected_loads[train_id]
        eligible = [
            pid for pid in self.waiting if self.people[pid].destination == destination
        ]
        expected = eligible[: capacity - initial_load]
        assert self.queue.board("P", train) == expected
        assert train.onboard_load == initial_load + len(expected)
        self.expected_loads[train_id] += len(expected)
        expected_set = set(expected)
        self.waiting = [pid for pid in self.waiting if pid not in expected_set]
        self.boarded.extend(expected)
        # A second call must neither duplicate boarding nor drop the unread tail.
        assert self.queue.board("P", train) == []

    @invariant()
    def identities_and_loads_are_conserved(self):
        """Preserve waiting/onboard identities and whole-vehicle load bounds."""
        assert self.queue.waiting_count("P") == len(self.waiting)
        assert len(self.boarded) == len(set(self.boarded))
        assert set(self.waiting).isdisjoint(self.boarded)
        assert set(self.waiting) | set(self.boarded) == set(self.people)
        assert all(
            self.people[pid].state is PassengerState.WAITING for pid in self.waiting
        )
        assert all(
            self.people[pid].state is PassengerState.ON_BOARD for pid in self.boarded
        )
        assert all(
            0 <= train.onboard_load <= train.capacity
            for train in self.vehicles.values()
        )


TestCapacityJourneys = CapacityJourneyMachine.TestCase
TestCapacityJourneys.settings = settings(
    max_examples=100,
    stateful_step_count=50,
    deadline=None,
    derandomize=True,
)
