# AI contribution: 50% or more AI-generated
"""Shared test fixtures.

The tiny network, minimal scenario and stream factory here stand in for the
network model (Task 1.1.4, #97), the scenario configuration (Task 1.1.5, #98)
and the seed manager (Task 1.1.3, #9) until those are merged. They only
provide what the runner reads, so the tests do not depend on how those tasks
are built.
"""

from collections import Counter
from dataclasses import dataclass

import pytest

from simulator.engine.event_queue import Scheduler
from simulator.engine.events import (
    Alighting,
    Boarding,
    DepartureDue,
    Event,
    Hold,
    HoldEnd,
    TrainArrival,
    TrainDeparture,
)

MASTER_SEED = 20261017


@dataclass(frozen=True)
class MinimalScenario:
    """Smallest scenario the runner accepts."""

    duration_s: float = 600.0
    master_seed: int = MASTER_SEED


@dataclass(frozen=True)
class SeedOnlyStreams:
    """Stand-in for the random substreams. Records the seed it was built from.

    The tiny network draws no random values, so no generator is needed.
    """

    master_seed: int


@dataclass(frozen=True)
class StopVisit:
    """One train calling at one platform. Times in seconds."""

    train_id: str
    station_id: str
    platform_id: str
    arrival_s: float
    dwell_s: float
    hold_s: float = 0.0


# One interchange (McGill), one REM line and one metro line (green). The REM
# platform ID is the real GTFS one; the metro platform ID is made up.
TINY_TIMETABLE = (
    StopVisit("green-1", "mcgill", "green-mcgill-west", 100.0, 20.0),
    StopVisit("rem-1", "mcgill", "STA_ZCD_BT_QUAI_01_MCG", 120.0, 30.0),
    StopVisit("green-2", "mcgill", "green-mcgill-west", 280.0, 20.0),
)

# rem-1 from the tiny timetable, held 40 s: arrives 120, dwell 30, departure
# due 150, leaves 190
HELD_REM_VISIT = StopVisit(
    "rem-1", "mcgill", "STA_ZCD_BT_QUAI_01_MCG", 120.0, 30.0, 40.0
)


class TimetableComponent:
    """Runs trains to the timetable, with a fixed hold instead of a strategy.

    Each train arrives on time and its departure becomes due after the dwell.
    A visit with ``hold_s`` 0 leaves at that instant; otherwise the hold is
    recorded and the train leaves when it ends. There are no disruptions, so
    every disruption delay is 0. Trains start empty, and the departure counts
    are the boardings and alightings seen for the train so far, taken when it
    actually leaves.
    """

    def __init__(self, visits: tuple[StopVisit, ...]) -> None:
        self._visits = {visit.train_id: visit for visit in visits}
        self._boarded: Counter[str] = Counter()
        self._alighted: Counter[str] = Counter()

    def start(self, scheduler: Scheduler) -> None:
        for visit in self._visits.values():
            scheduler.schedule(
                TrainArrival(
                    time_s=visit.arrival_s,
                    train_id=visit.train_id,
                    station_id=visit.station_id,
                    platform_id=visit.platform_id,
                    scheduled_s=visit.arrival_s,
                    disruption_delay_s=0.0,
                )
            )

    def handle(self, event: Event, scheduler: Scheduler) -> None:
        if isinstance(event, Boarding):
            self._boarded[event.train_id] += 1
        elif isinstance(event, Alighting):
            self._alighted[event.train_id] += 1
        elif isinstance(event, TrainArrival):
            visit = self._visits[event.train_id]
            scheduler.schedule(
                DepartureDue(
                    time_s=event.time_s + visit.dwell_s,
                    scheduled_s=visit.arrival_s + visit.dwell_s,
                    **self._where(visit),
                )
            )
        elif isinstance(event, DepartureDue):
            self._decide_hold(self._visits[event.train_id], event.time_s, scheduler)
        elif isinstance(event, HoldEnd):
            self._depart(self._visits[event.train_id], event.time_s, scheduler)

    def _decide_hold(
        self, visit: StopVisit, now_s: float, scheduler: Scheduler
    ) -> None:
        if visit.hold_s == 0:
            self._depart(visit, now_s, scheduler)
            return
        where = self._where(visit)
        scheduler.schedule(
            Hold(
                time_s=now_s,
                requested_s=visit.hold_s,
                applied_s=visit.hold_s,
                reason="fixed test hold",
                **where,
            )
        )
        scheduler.schedule(HoldEnd(time_s=now_s + visit.hold_s, **where))

    def _depart(self, visit: StopVisit, now_s: float, scheduler: Scheduler) -> None:
        boarded = self._boarded[visit.train_id]
        alighted = self._alighted[visit.train_id]
        scheduler.schedule(
            TrainDeparture(
                time_s=now_s,
                scheduled_s=visit.arrival_s + visit.dwell_s,
                disruption_delay_s=0.0,
                hold_s=visit.hold_s,
                boarded_count=boarded,
                alighted_count=alighted,
                onboard_load=boarded - alighted,
                **self._where(visit),
            )
        )

    @staticmethod
    def _where(visit: StopVisit) -> dict[str, str]:
        return {
            "train_id": visit.train_id,
            "station_id": visit.station_id,
            "platform_id": visit.platform_id,
        }


@pytest.fixture
def minimal_scenario():
    return MinimalScenario()


@pytest.fixture
def build_streams():
    """Stream factory with the signature the runner expects."""
    return SeedOnlyStreams


@pytest.fixture
def build_tiny_network():
    """Component factory that runs the tiny timetable."""

    def build(_scenario, _streams):
        return [TimetableComponent(TINY_TIMETABLE)]

    return build


@pytest.fixture
def held_rem_component():
    """Train component running only rem-1, held 40 s (``HELD_REM_VISIT``)."""
    return TimetableComponent((HELD_REM_VISIT,))
