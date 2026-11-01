# AI contribution: 50% or more AI-generated
"""US-2.3 #47: test when trains should wait for scheduled departure.

Covers early, on-time and late trains, final stops and fractional holds.
Passenger loads and transfers must not change the decision.
"""

import dataclasses

import pytest

from simulator.control.decision import DecisionPipeline, HoldDecision
from simulator.control.interface import (
    HoldAction,
    IncomingTransfer,
    ObservationSnapshot,
    TrainState,
)
from simulator.control.strategies.schedule_based_holding import (
    ScheduleBasedHoldingStrategy,
)
from simulator.engine.event_queue import Scheduler
from simulator.engine.events import DepartureDue
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


def make_snapshot(time_s=120, scheduled_departure_s=130, onboard_load=0, transfers=()):
    """Build a decision at P1, with the next departure scheduled 100 s later."""
    # Give the next stop a different timetable so confusing the two schedules
    # produces a visibly wrong hold: 110 seconds instead of 10.
    return ObservationSnapshot(
        time_s=time_s,
        train_id="A",
        station_id="S1",
        platform_id="P1",
        scheduled_departure_s=scheduled_departure_s,
        trains=(
            TrainState(
                train_id="A",
                line_id="rem",
                next_platform_id="P2",
                predicted_arrival_s=time_s + 70,
                scheduled_departure_s=scheduled_departure_s + 100,
                delay_s=time_s - scheduled_departure_s,
                onboard_load=onboard_load,
                capacity=800,
            ),
        ),
        platforms=(),
        incoming_transfers=transfers,
    )


# Check fractional holds without rounding to whole seconds.
@pytest.mark.parametrize(
    ("time_s", "scheduled_departure_s", "expected"),
    [
        (120, 130, (HoldAction("A", 10, "schedule_based"),)),
        (130, 130, ()),
        (140, 130, ()),
        (129.75, 130, (HoldAction("A", 0.25, "schedule_based"),)),
        (250, 270, (HoldAction("A", 20, "schedule_based"),)),
    ],
    ids=["early", "on_time", "late", "fractional_hold", "different_timetable"],
)
def test_schedule_hold_matches_readiness(time_s, scheduled_departure_s, expected):
    """Wait only for the positive remainder until the supplied timetable time."""
    observation = make_snapshot(
        time_s=time_s, scheduled_departure_s=scheduled_departure_s
    )
    assert ScheduleBasedHoldingStrategy().evaluate(observation) == expected


@pytest.mark.parametrize("final_stop", [False, True])
def test_schedule_policy_uses_current_departure_in_pipeline(final_stop):
    """At readiness 120, hold 10 s whether the next departure is 230 or absent."""
    schedule = (ScheduledStop("S1", "P1", 100, 130),)
    if not final_stop:
        schedule += (ScheduledStop("S2", "P2", 200, 230),)
    train = Train(id="A", capacity=800, schedule=schedule, current_delay=-10)
    component = TrainComponent([train])
    pipeline = DecisionPipeline(strategy=ScheduleBasedHoldingStrategy())
    scheduler = Scheduler()
    decisions = []
    component.start(scheduler)

    def process(event):
        # Record the holding decision without applying it to train movement.
        if isinstance(event, DepartureDue):
            decisions.append(pipeline.decide(event, component))
        component.handle(event, scheduler)

    scheduler.run_until(120, process)
    assert decisions == [HoldDecision(10, 10, "schedule_based")]


@pytest.mark.parametrize("onboard_load", [0, 800])
@pytest.mark.parametrize(
    "transfers",
    [(), (IncomingTransfer("group-1", "P1", 200, 125, 160),)],
)
def test_schedule_policy_ignores_transfer_and_load_changes(onboard_load, transfers):
    """An empty or full train requests the same hold, with or without transfers."""
    observation = make_snapshot(onboard_load=onboard_load, transfers=transfers)
    # Comparing values before and after also protects the read-only contract.
    before = dataclasses.asdict(observation)
    actions = ScheduleBasedHoldingStrategy().evaluate(observation)
    assert actions == (HoldAction("A", 10, "schedule_based"),)
    assert dataclasses.asdict(observation) == before
