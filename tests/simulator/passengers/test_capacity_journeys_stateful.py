# AI contribution: 50% or more AI-generated
"""Extend the #24 LLL prototype to tracked journeys and successive trains.

The independent model retains incompatible destinations and capacity overflow.
Generated trains alternate freely between routes; waiting IDs must survive until
a compatible train with space arrives. No private production queue is inspected.
"""

from itertools import product

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    precondition,
    rule,
)

from simulator.engine.events import PassengerArrival, TrainArrival
from simulator.passengers import Passenger, PassengerState
from simulator.passengers.platform_queue import PlatformQueue
from simulator.trains.train import ScheduledStop, Train

MAX_STEPS = 50


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
        self.completed = set()
        self.onboard_by_train = {}
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
                tuple(
                    ScheduledStop(
                        "A" if index % 2 == 0 else destination,
                        "P" if index % 2 == 0 else destination,
                        index * 20,
                        index * 20 + 10,
                    )
                    for index in range(2 * (MAX_STEPS + 1))
                ),
                onboard_load=load,
            )
            self.expected_loads[train_id] = load
            self.onboard_by_train[train_id] = []
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
        self.onboard_by_train[train_id].extend(expected)
        # A second call must neither duplicate boarding nor drop the unread tail.
        assert self.queue.board("P", train) == []

    @precondition(lambda self: any(self.onboard_by_train.values()))
    @rule(data=st.data())
    def alight_at_destination(self, data):
        """Select a train carrying tracked riders, so alighting is meaningful."""
        occupied = [key for key, ids in self.onboard_by_train.items() if ids]
        self._alight_train(data.draw(st.sampled_from(occupied)))

    def _alight_train(self, train_id):
        """Drive destination arrival, then advance to its next origin visit.

        This queue-level model supplies stop progression; scheduler integration
        remains covered by test_boarding.py. Aggregate riders keep their seats.
        """
        train = self.vehicles[train_id]
        train.current_stop_index += 1
        stop = train.current_stop
        expected = self.onboard_by_train[train_id][:]
        records = self.queue.train_arrival(
            TrainArrival(
                time_s=stop.arrival_s,
                train_id=train.id,
                station_id=stop.station_id,
                platform_id=stop.platform_id,
                scheduled_s=stop.arrival_s,
                disruption_delay_s=0,
            ),
            train,
        )
        assert [event.passenger_id for event in records] == expected
        assert all(event.train_id == train_id for event in records)
        assert all(event.platform_id == stop.platform_id for event in records)
        assert self.queue.alighted_count(train_id) == len(expected)
        self.expected_loads[train_id] -= len(expected)
        assert train.onboard_load == self.expected_loads[train_id]
        self.completed.update(expected)
        self.boarded = [pid for pid in self.boarded if pid not in self.completed]
        self.onboard_by_train[train_id] = []
        # Return to A using the next actual stop, without resetting queue state.
        train.current_stop_index += 1

    @invariant()
    def identities_and_loads_are_conserved(self):
        """Preserve waiting/onboard identities and whole-vehicle load bounds."""
        assert self.queue.waiting_count("P") == len(self.waiting)
        assert len(self.boarded) == len(set(self.boarded))
        assert set(self.waiting).isdisjoint(self.boarded)
        assert self.completed.isdisjoint(self.waiting)
        assert self.completed.isdisjoint(self.boarded)
        assert set(self.waiting) | set(self.boarded) | self.completed == set(
            self.people
        )
        assert all(
            self.people[pid].state is PassengerState.COMPLETED for pid in self.completed
        )
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
        assert all(
            train.onboard_load == self.expected_loads[key]
            for key, train in self.vehicles.items()
        )


TestCapacityJourneys = CapacityJourneyMachine.TestCase
TestCapacityJourneys.settings = settings(
    max_examples=100,
    stateful_step_count=MAX_STEPS,
    deadline=None,
    derandomize=True,
)


def test_alighting_frees_seats_for_waiting_passengers_in_order():
    """Force two full boarding/alighting cycles, including a skipped destination."""
    machine = CapacityJourneyMachine()
    try:
        machine.setup()
        for destination in ("B", "C", "B", "B", "B"):
            machine.arrive(destination)
        machine.serve("B", 3, 50)  # One aggregate rider leaves two spaces.
        assert machine.boarded == ["p0", "p2"]
        machine._alight_train("B-3-50")
        machine.identities_and_loads_are_conserved()
        assert machine.vehicles["B-3-50"].onboard_load == 1
        machine.serve("B", 3, 50)
        assert machine.boarded == ["p3", "p4"]
        machine._alight_train("B-3-50")
        machine.identities_and_loads_are_conserved()
        assert machine.completed == {"p0", "p2", "p3", "p4"}
        assert machine.waiting == ["p1"]
        machine.serve("C", 1, 0)
        machine.identities_and_loads_are_conserved()
        assert machine.boarded == ["p1"]
    finally:
        machine.teardown()
