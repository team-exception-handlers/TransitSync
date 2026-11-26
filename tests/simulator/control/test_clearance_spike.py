# AI contribution: 50% or more AI-generated
"""Paired clearance and boarding evidence for US-2.4 (#206) and LLL #340.

Times are simulation seconds. Fresh trains and queues isolate each paired run.
Walkers always have available seats, without boarding capacity bottlenecks.
"""

from dataclasses import dataclass
from typing import ClassVar

import pytest

from simulator.control.break_even import BreakEvenWeights
from simulator.control.decision import DecisionPipeline
from simulator.control.expected_arrivals import expected_caught
from simulator.control.hold_search import HoldSearch, HoldSearchSettings
from simulator.control.interface import (
    DecisionController,
    HoldAction,
    IncomingTransfer,
    ObservationSnapshot,
    as_actions,
)
from simulator.control.observation_builder import ObservationBuilder
from simulator.control.strategies.connection_protection import (
    ConnectionProtectionStrategy,
)
from simulator.engine.event_queue import Scheduler
from simulator.engine.events import (
    Boarding,
    Event,
    Hold,
    PassengerArrival,
    TrainDeparture,
)
from simulator.passengers.platform_queue import PlatformQueue
from simulator.trains.suspension import LineSuspension, dispatch_ready_s
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


@dataclass(frozen=True)
class FixedHold(DecisionController):
    """Test-only Strategy: request a known wait without accessing engine state."""

    duration_s: float
    name: ClassVar[str] = "clearance_spike"

    def evaluate(self, observation: ObservationSnapshot) -> tuple[HoldAction, ...]:
        """Request duration_s seconds from readiness, or no action for zero."""
        action = None
        if self.duration_s > 0 and observation.train_id == "A":
            action = HoldAction(observation.train_id, self.duration_s, self.name)
        return as_actions(action)


def run_departure(
    hold_s: float,
    walker_s: float,
    suspensions: tuple[LineSuspension, ...],
    *,
    ready_s=0,
    previous_s=None,
    controller=None,
    transfer_sources=(),
    load=1,
    walker_count=1,
) -> tuple[float, bool]:
    """Return actual departure seconds and whether the walker boarded.

    Fresh vehicles/queues isolate the counterfactual from the preceding run.
    Ready/previous times are seconds; each train begins at a dispatch-limited origin.
    Hold evidence must show the requested intervention even when mandatory
    waiting makes the paired departure and boarding outcomes identical.
    """
    component = TrainComponent(
        paired_trains(ready_s, previous_s, load, walker_count),
        decision=DecisionPipeline(
            controller or FixedHold(hold_s),
            builder=ObservationBuilder(transfer_sources),
        ),
        passenger_queue=PlatformQueue(("P",)),
        suspensions=suspensions,
    )
    scheduler = Scheduler()
    component.start(scheduler)
    for index in range(walker_count):
        scheduler.schedule(
            PassengerArrival(
                time_s=walker_s,
                passenger_id=f"walker-{index}",
                group_id="burst",
                platform_id="P",
            )
        )
    events: list[Event] = []

    def process(event: Event) -> None:
        events.append(event)
        component.handle(event, scheduler)

    scheduler.run_until(600, process)
    if previous_s is not None:
        [leader] = [
            e
            for e in events
            if isinstance(e, TrainDeparture) and e.train_id == "leader"
        ]
        assert leader.time_s == previous_s
    return departure_outcome(events, hold_s, walker_count)


def paired_trains(ready_s, previous_s, load, walker_count):
    """Keep the predecessor arrival early so only its departure gap constrains A."""
    trains = [
        Train(
            "A",
            load + walker_count,
            (ScheduledStop("S", "P", ready_s, ready_s),),
            line_id="green",
            onboard_load=load,
        )
    ]
    if previous_s is not None:
        trains.insert(
            0,
            Train(
                "leader",
                1,
                (ScheduledStop("S", "P", 0, previous_s),),
                line_id="green",
            ),
        )
    return trains


def departure_outcome(events, hold_s, walker_count):
    """Check the applied intervention before comparing departure/boarding outcomes."""
    # An absorbed hold leaves departure/boarding unchanged, so prove it was applied.
    holds = [event for event in events if isinstance(event, Hold)]
    if hold_s > 0:
        [hold] = holds
        assert hold.requested_s == hold_s
        assert hold.applied_s == hold_s
    else:
        assert holds == []
    [departure] = [
        event
        for event in events
        if isinstance(event, TrainDeparture) and event.train_id == "A"
    ]
    boarded = any(
        isinstance(event, Boarding) and event.train_id == "A" for event in events
    )
    assert departure.boarded_count == (walker_count if boarded else 0)
    return departure.time_s, boarded


@pytest.mark.parametrize(
    ("suspended", "hold_s", "walker_s", "departures", "boarding", "saved", "delay_s"),
    [
        (True, 20, 15, (30, 30), (True, True), 0, 0),
        (True, 45, 35, (30, 45), (False, True), 1, 15),
        (False, 20, 15, (0, 20), (False, True), 1, 20),
    ],
    ids=["absorbed", "extends_suspension", "no_suspension"],
)
def test_departure_estimate_matches_dispatch_outcome(
    suspended, hold_s, walker_s, departures, boarding, saved, delay_s
):
    """Check each #340 hand calculation against departure and boarding events."""
    suspensions = (LineSuspension("green", 0, 30),) if suspended else ()
    # Predict first from known origin/line/restriction inputs, not future events.
    baseline = dispatch_ready_s("green", 0, suspensions)
    projected = dispatch_ready_s("green", hold_s, suspensions)
    # Suspended: D0=30 and D(h)=max(h,30); otherwise D0=0 and D(h)=h.
    assert (baseline, projected) == departures
    unheld, boards_unheld = run_departure(0, walker_s, suspensions)
    held, boards_held = run_departure(hold_s, walker_s, suspensions)
    assert (unheld, held) == departures
    assert (boards_unheld, boards_held) == boarding
    # Saved connections are the difference in paired boarding outcomes;
    # each original onboard passenger experiences held minus unheld departure.
    assert int(boards_held) - int(boards_unheld) == saved
    assert held - unheld == delay_s


@dataclass(frozen=True)
class KnownWalker:
    """Deterministic test CDF: one walker finishes arrival_s after the feeder."""

    arrival_s: float

    def cdf(self, time_s: float) -> float:
        """Return the share arrived by time_s seconds, including equality."""
        return float(time_s >= self.arrival_s)


def test_readiness_baseline_credits_connection_without_changing_boarding():
    """The current estimator credits one connection that both runs already make.

    Keep this diagnostic passing: it records the known limitation, without
    changing production scoring or leaving an intentionally failing test.
    """
    suspensions = (LineSuspension("green", 0, 30),)
    unheld, boards_unheld = run_departure(0, 15, suspensions)
    held, boards_held = run_departure(20, 15, suspensions)
    readiness_caught = expected_caught(1, 0, 20, KnownWalker(15))
    # M*[F(0+20)-F(0)] = 1*(1-0) = 1 using the old readiness window.
    assert readiness_caught == 1
    assert (unheld, held) == (30, 30)
    assert (boards_unheld, boards_held) == (True, True)
    # Actual extra connections = 1-1 = 0; added onboard delay = 30-30 = 0.
    assert int(boards_held) - int(boards_unheld) == 0
    assert held - unheld == 0


@pytest.mark.parametrize(
    ("walker_s", "boarding"),
    [
        (140, (True, True)),
        (150, (False, True)),
        (160, (False, True)),
    ],
)
def test_boarding_at_projected_departure_boundaries(walker_s, boarding):
    """Arrivals at departure time board before doors close in both paired runs."""
    closure = (LineSuspension("green", 100, 140),)
    baseline = run_departure(0, walker_s, closure, ready_s=100)
    held = run_departure(60, walker_s, closure, ready_s=100)
    assert (baseline[0], held[0]) == (140, 160)
    assert (baseline[1], held[1]) == boarding


@pytest.mark.parametrize(("hold_s", "departure"), [(40, 142.5), (45, 145)])
def test_fractional_minimum_gap_matches_paired_departures(hold_s, departure):
    """Dispatch clears at 120, then the predecessor gap requires 52.5+90."""
    closure = (LineSuspension("green", 100, 120),)
    baseline = run_departure(0, 144, closure, ready_s=100, previous_s=52.5)
    held = run_departure(hold_s, 144, closure, ready_s=100, previous_s=52.5)
    assert baseline == (142.5, False)
    assert held == (departure, hold_s == 45)


@dataclass(frozen=True)
class PulseSource:
    """Known feeder burst: 100 walkers arrive at 400 s after feeder time zero."""

    def incoming_transfers(self):
        """Supply the same pulse to the observation builder for each paired run."""
        return (IncomingTransfer("burst", "P", 100, 400, 400, 0, 100),)


def test_connection_strategy_selects_shortest_hold_entering_later_suspension():
    """A real strategy chooses 20 s, whose departure delay is 170 s (#206)."""
    strategy = ConnectionProtectionStrategy(
        {
            "P": HoldSearch(
                KnownWalker(400), BreakEvenWeights(1, 1), HoldSearchSettings(5, 120)
            )
        },
        {"P": 300},
    )
    closure = (LineSuspension("green", 300, 450),)
    baseline = run_departure(0, 400, closure, ready_s=280, load=100, walker_count=100)
    held = run_departure(
        20,
        400,
        closure,
        ready_s=280,
        load=100,
        walker_count=100,
        controller=strategy,
        transfer_sources=(PulseSource(),),
    )
    assert baseline == (280, False)
    assert held == (450, True)
    [record] = strategy.decision_records()
    assert record["chosen_hold_s"] == 20
    assert record["no_hold_departure_s"] == 280
    assert [c["hold_s"] for c in record["candidates"]] == list(range(0, 121, 5))
    for candidate in record["candidates"][4:]:
        # All requests 20..120 enter [300,450): 100*300 - 100*(450-280).
        assert candidate["departure_s"] == 450
        assert candidate["incremental_delay_s"] == 170
        assert candidate["n_caught"] == 100
        assert candidate["benefit_ps"] == 30000
        assert candidate["cost_ps"] == 17000
        assert candidate["net_ps"] == 13000
    assert [c["n_caught"] for c in record["candidates"][:4]] == [0, 0, 0, 0]
