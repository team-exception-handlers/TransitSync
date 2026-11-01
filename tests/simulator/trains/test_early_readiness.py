# AI contribution: 50% or more AI-generated
"""US-2.3 #47: trains can be ready to leave before their scheduled departure.

These tests check early, on-time and late trains using expected times worked
out by hand. The timetable stays unchanged while actual movement times vary.

Generated cases run two to four trains through the real train component.
Each case starts fresh, keeps events in memory and runs long enough for every
train to finish. We check that all expected arrivals and departures happened
before checking the gaps between trains, so an incomplete run fails the test.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulator.engine.event_queue import Scheduler
from simulator.engine.events import DepartureDue, Event, TrainArrival, TrainDeparture
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


def make_train(train_id: str, arrival_s: float, deviation_s: float) -> Train:
    """Build a fresh two-stop train with a signed initial deviation in seconds."""
    return Train(
        id=train_id,
        capacity=800,
        schedule=(
            ScheduledStop("S1", "P1", arrival_s, arrival_s + 30),
            ScheduledStop("S2", "P2", arrival_s + 100, arrival_s + 130),
        ),
        current_delay=deviation_s,
        # Earliness is schedule deviation, never negative generated lateness.
        generated_delay_s=max(0.0, deviation_s),
    )


def run_trains(trains: list[Train], minimum_gap_s: float = 90) -> list[Event]:
    """Process real movements to completion within the small fixture's horizon.

    The callback records each processed event before dispatch. Keeping this
    in memory makes every generated example independent of temporary paths.
    """
    component = TrainComponent(trains, minimum_gap_s=minimum_gap_s)
    scheduler = Scheduler()
    records: list[Event] = []
    component.start(scheduler)

    def process(event: Event) -> None:
        records.append(event)
        component.handle(event, scheduler)

    scheduler.run_until(5000, process)
    return records


def assert_safe_movements(records, platform, event_class, expected_ids, minimum_gap_s):
    """Check complete per-platform movement order before consecutive gaps.

    Expected identities catch missing and duplicated visits. Adjacent times
    alone could pass if the engine emitted no movements at all.
    """
    movements = [
        event
        for event in records
        if isinstance(event, event_class) and event.platform_id == platform
    ]
    assert [event.train_id for event in movements] == expected_ids
    for previous, current in zip(movements, movements[1:], strict=False):
        assert current.time_s - previous.time_s >= minimum_gap_s


@pytest.mark.parametrize(
    ("deviation_s", "expected"),
    [
        (-10, [(90, 120), (190, 220)]),
        (0, [(100, 130), (200, 230)]),
        (10, [(110, 140), (210, 240)]),
    ],
)
def test_no_control_preserves_signed_initial_deviation(deviation_s, expected):
    """Preserve the initial offset while retaining the timetable for holding."""
    train = make_train("A", 100, deviation_s)
    original_schedule = train.schedule
    records = run_trains([train])
    arrivals = [event.time_s for event in records if isinstance(event, TrainArrival)]
    departures = [
        event.time_s for event in records if isinstance(event, TrainDeparture)
    ]
    assert list(zip(arrivals, departures, strict=True)) == expected
    assert train.schedule == original_schedule
    # Readiness follows the hand-calculated departures; timetable targets stay
    # at 130 and 230 even when the early train is ready at 120 and 220.
    decisions = [
        (event.train_id, event.platform_id, event.time_s, event.scheduled_s)
        for event in records
        if isinstance(event, DepartureDue)
    ]
    assert decisions == [
        ("A", "P1", expected[0][1], 130),
        ("A", "P2", expected[1][1], 230),
    ]


def test_early_initial_arrival_stays_at_or_after_simulation_start():
    """A nominal arrival at -5 is bounded at zero, then receives its full dwell."""
    records = run_trains([make_train("A", 5, -10)])
    arrivals = [event.time_s for event in records if isinstance(event, TrainArrival)]
    departures = [
        event.time_s for event in records if isinstance(event, TrainDeparture)
    ]
    assert arrivals == [0, 100]
    assert departures == [30, 130]
    assert min(event.time_s for event in records) == 0


def test_early_follower_still_respects_platform_clearance():
    """Follower's natural 140 arrival waits until 90 seconds after the leader."""
    records = run_trains([make_train("A", 100, -10), make_train("B", 190, -50)])
    first_stop = [
        (event.train_id, event.time_s)
        for event in records
        if isinstance(event, TrainArrival | TrainDeparture)
        and event.platform_id == "P1"
    ]
    assert first_stop == [("A", 90), ("A", 120), ("B", 180), ("B", 210)]


@settings(max_examples=40)
@given(
    deviations=st.lists(st.integers(-100, 100), min_size=2, max_size=4),
    minimum_gap_s=st.integers(1, 90),
)
def test_generated_early_runs_respect_operating_gaps(deviations, minimum_gap_s):
    """Small generated runs must finish every visit and preserve safe ordering."""
    trains = [
        make_train(str(index), 300 + index * 200, deviation)
        for index, deviation in enumerate(deviations)
    ]
    records = run_trains(trains, minimum_gap_s)
    times = [event.time_s for event in records]
    assert times == sorted(times)
    expected_ids = [train.id for train in trains]
    # Pin every visit before pairwise assertions: missing events must fail too.
    for platform in ("P1", "P2"):
        for event_class in (TrainArrival, TrainDeparture):
            assert_safe_movements(
                records, platform, event_class, expected_ids, minimum_gap_s
            )
