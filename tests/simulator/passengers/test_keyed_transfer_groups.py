# AI contribution: 50% or more AI-generated
"""Transfer groups drawn from the feeder arrival they belong to (#192).

Section 9 pairs runs on the same seed. A group's size, destinations and walks
must not depend on how many other groups drew before it, or a hold that adds
or moves another group changes this one too.
"""

from simulator.engine.event_queue import Scheduler
from simulator.engine.random_streams import StreamManager
from simulator.passengers import CorridorQueue, TransferComponent
from tests.simulator.passengers.test_transfer_component import (
    advance,
    feeder,
    route,
)


def walks_by_group(arrivals):
    """Run the feeder arrivals; return each group's walk ends in passenger order."""
    # Corridors keep state, so every run builds fresh routes
    bonaventure = route(
        station_id="bonaventure",
        feeder_platform_id="rem-b",
        connecting_platform_id="orange",
        transfer_fractions={"mcgill": 1},
        corridor=CorridorQueue(6000),
    )
    component = TransferComponent([route(), bonaventure], StreamManager(42))
    scheduler = Scheduler()
    for arrival in arrivals:
        scheduler.schedule(arrival)
    advance(component, scheduler, 2000)
    groups = {}
    for _, walk in sorted(component.walk_records().items()):
        groups.setdefault(walk.group_id, []).append(walk.corridor_arrival_s)
    return groups


def test_group_draws_ignore_groups_drawn_before_it():
    # The Bonaventure group draws first in one run only; McGill's group must
    # get the same size and walks in both (one shared stream shifted them)
    mcgill = feeder(100)
    alone = walks_by_group([mcgill])
    after_other = walks_by_group(
        [feeder(50, station_id="bonaventure", platform_id="rem-b"), mcgill]
    )
    group = "passenger-group-mcgill-rem-100-1"
    assert len(alone[group]) > 10
    assert after_other[group] == alone[group]
    assert len(after_other) == 2


def test_repeat_visits_of_one_train_are_separate_groups():
    # Edge: the same train at the same station twice gets two keys, so two
    # groups with their own draws instead of one merged group
    groups = walks_by_group(
        [feeder(100, train_id="rem-1"), feeder(400, train_id="rem-1")]
    )
    assert set(groups) == {
        "passenger-group-mcgill-rem-1-1",
        "passenger-group-mcgill-rem-1-2",
    }
    assert (
        groups["passenger-group-mcgill-rem-1-1"]
        != groups["passenger-group-mcgill-rem-1-2"]
    )


def mcgill_ids(arrivals):
    """Run the feeder arrivals; return the IDs in McGill's group, in ID order."""
    component = TransferComponent(
        [
            route(),
            route(
                station_id="bonaventure",
                feeder_platform_id="rem-b",
                transfer_fractions={"mcgill": 1},
            ),
        ],
        StreamManager(42),
    )
    scheduler = Scheduler()
    for arrival in arrivals:
        scheduler.schedule(arrival)
    advance(component, scheduler, 2000)
    group = "passenger-group-mcgill-rem-100-1"
    walks = component.walk_records().items()
    return sorted(pid for pid, walk in walks if walk.group_id == group)


def test_passenger_ids_ignore_groups_drawn_before_them():
    # A run-wide counter gave McGill's group new IDs once Bonaventure's group
    # drew first, so paired runs could not match the same person (#240)
    mcgill = feeder(100)
    alone = mcgill_ids([mcgill])
    after_other = mcgill_ids(
        [feeder(50, station_id="bonaventure", platform_id="rem-b"), mcgill]
    )
    assert after_other == alone
    assert alone[:2] == [
        "passenger-mcgill-rem-100-1-0001",
        "passenger-mcgill-rem-100-1-0002",
    ]
