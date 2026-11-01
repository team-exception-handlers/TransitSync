# AI contribution: 50% or more AI-generated
"""Tests for the observation builder (US-2.1, Task 2.1.2, #38)."""

import dataclasses

from simulator.control.interface import (
    IncomingTransfer,
    ObservationSnapshot,
    PlatformState,
    TrainState,
)
from simulator.control.observation_builder import ObservationBuilder
from simulator.engine.event_queue import Scheduler
from simulator.engine.events import DepartureDue
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


class FixedTransfers:
    """Transfer source returning one walking group."""

    def incoming_transfers(self):
        return (IncomingTransfer("group-1", "P2", 12, 140.0, 190.0),)


def make_trains(initial_deviation_s=0):
    # A: P1 100-130, then P2 200-230. B: P1 400-430, starting 60 s late
    first = Train(
        id="A",
        capacity=800,
        schedule=(
            ScheduledStop("S1", "P1", 100, 130),
            ScheduledStop("S2", "P2", 200, 230),
        ),
        line_id="rem",
        current_delay=initial_deviation_s,
        generated_delay_s=max(0.0, initial_deviation_s),
    )
    second = Train(
        id="B",
        capacity=600,
        schedule=(ScheduledStop("S1", "P1", 400, 430),),
        current_delay=60.0,
        generated_delay_s=60.0,
        line_id="rem",
    )
    return [first, second]


def snapshots_at_each_decision(transfer_sources=(), initial_deviation_s=0):
    """Run the trains and build a snapshot at every ``DepartureDue``."""
    component = TrainComponent(make_trains(initial_deviation_s))
    builder = ObservationBuilder(transfer_sources)
    scheduler = Scheduler()
    component.start(scheduler)
    snapshots: list[ObservationSnapshot] = []

    def process(event):
        if isinstance(event, DepartureDue):
            snapshots.append(builder.build(event, component))
        component.handle(event, scheduler)

    scheduler.run_until(1000.0, process)
    return snapshots


def test_snapshot_at_first_decision_has_hand_calculated_values():
    first = snapshots_at_each_decision()[0]
    assert (first.time_s, first.train_id, first.platform_id) == (130.0, "A", "P1")
    # A is dwelling at P1, so its next stop is P2 on the timetable
    assert first.trains[0] == TrainState("A", "rem", "P2", 200.0, 230.0, 0.0, 0, 800)
    # B has not arrived: planned arrival is 400 s + 60 s late
    assert first.trains[1] == TrainState("B", "rem", "P1", 460.0, 430.0, 60.0, 0, 600)
    assert first.platforms == (
        PlatformState("P1", 0, None),
        PlatformState("P2", 0, None),
    )


def test_later_decisions_see_departures_and_finished_trains():
    _, at_p2, last = snapshots_at_each_decision()
    # At A's last stop it has no next stop; P1 records A's departure at 130 s
    assert at_p2.trains[0].next_platform_id is None
    assert at_p2.platforms[0] == PlatformState("P1", 0, 130.0)
    # By B's decision, A has left the network for good
    assert last.trains[0].predicted_arrival_s is None
    assert last.time_s == 490.0


def test_early_decision_predicts_early_next_arrival():
    """An early departure predicts 190 at P2, not a silent wait until 200."""
    first = snapshots_at_each_decision(initial_deviation_s=-10)[0]
    assert first.time_s == 120
    assert first.trains[0].predicted_arrival_s == 190
    assert first.trains[0].scheduled_departure_s == 230


def test_builder_exposes_current_departure_schedule():
    """The deciding stop departs at 130; the following stop departs at 230."""
    first = snapshots_at_each_decision(initial_deviation_s=-10)[0]
    assert first.scheduled_departure_s == 130
    assert first.trains[0].scheduled_departure_s == 230


def test_builder_keeps_current_departure_schedule_at_final_stop():
    """A final stop still has a timetable even though there is no next stop."""
    _, last_stop, _ = snapshots_at_each_decision(initial_deviation_s=-10)
    assert last_stop.time_s == 220
    assert last_stop.scheduled_departure_s == 230
    assert last_stop.trains[0].scheduled_departure_s is None


def test_snapshot_does_not_change_as_the_run_continues():
    first = snapshots_at_each_decision()[0]
    # The run finished A's trip after this snapshot, yet it still shows P2 next
    assert first.trains[0].next_platform_id == "P2"


def test_transfer_groups_come_from_every_source():
    first = snapshots_at_each_decision((FixedTransfers(), FixedTransfers()))[0]
    expected = IncomingTransfer("group-1", "P2", 12, 140.0, 190.0)
    assert first.incoming_transfers == (expected, expected)


def test_no_transfer_sources_gives_no_incoming_transfers():
    first = snapshots_at_each_decision()[0]
    assert first.incoming_transfers == ()


def test_snapshot_values_are_plain_immutable_data():
    first = snapshots_at_each_decision((FixedTransfers(),))[0]
    parts = (*first.trains, *first.platforms, *first.incoming_transfers)
    for part in parts:
        for value in dataclasses.astuple(part):
            # Only numbers, text or None: nothing that points into the simulator
            assert value is None or isinstance(value, int | float | str)
