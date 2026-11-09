"""Verify transfer walk snapshots remain available after corridor admission.

The component is driven through its scheduler so the test covers both active
walks and fully completed walks without invoking the full scenario runner.
The fixed seed and large corridor capacity keep the test independent of timing races.
"""

import pytest

from simulator.engine.event_queue import Scheduler
from simulator.engine.events import TrainArrival
from simulator.engine.random_streams import StreamManager
from simulator.passengers import (
    CorridorQueue,
    DemandPeriod,
    DemandProfile,
    TransferComponent,
    TransferRoute,
)


def test_walk_records_preserve_all_walks_in_an_immutable_snapshot() -> None:
    """Keep immutable group and corridor timing after all walks have completed.

    The route's feeder train creates a seeded pulse; the scheduler advances
    through each passenger's walk, corridor passage, and platform arrival.
    Completion removes active state but must not remove historical map data.
    The returned mapping and its frozen records remain safe for API serialization.
    """
    route = TransferRoute(
        station_id="mcgill",
        feeder_platform_id="rem",
        connecting_platform_id="green",
        demand_profile=DemandProfile((DemandPeriod(0, 1000, 60),)),
        transfer_fractions={"bonaventure": 1.0},
        corridor=CorridorQueue(6000),
        walking_mean_s=10,
        walking_min_s=0,
    )
    component = TransferComponent([route], StreamManager(42))
    scheduler = Scheduler()
    scheduler.schedule(
        TrainArrival(
            time_s=100,
            scheduled_s=100,
            train_id="rem-100",
            station_id="mcgill",
            platform_id="rem",
            disruption_delay_s=0,
        )
    )

    def handle(event):
        component.handle(event, scheduler)

    scheduler.run_until(1000, handle)
    snapshot = component.walk_records()

    assert snapshot
    assert {walk.group_id for walk in snapshot.values()} == {"passenger-group-000001"}
    assert component.incoming_transfers() == ()
    with pytest.raises(TypeError):
        snapshot["extra"] = next(iter(snapshot.values()))
    assert component.walk_records() == snapshot
