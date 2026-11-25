# AI contribution: 50% or more AI-generated
"""LLL #340: validate dispatch estimates before changing US-2.4 (#206).

Times are seconds relative to readiness. Each paired run has one onboard
passenger and one walker with an available seat, without capacity bottlenecks.
"""

from dataclasses import dataclass
from typing import ClassVar

import pytest

from simulator.control.decision import DecisionPipeline
from simulator.control.expected_arrivals import expected_caught
from simulator.control.interface import (
    DecisionController,
    HoldAction,
    ObservationSnapshot,
    as_actions,
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
        if self.duration_s > 0:
            action = HoldAction(observation.train_id, self.duration_s, self.name)
        return as_actions(action)


def run_departure(
    hold_s: float, walker_s: float, suspensions: tuple[LineSuspension, ...]
) -> tuple[float, bool]:
    """Return actual departure seconds and whether the walker boarded.

    Fresh vehicles/queues isolate the counterfactual from the preceding run.
    The single current trip starts at the dispatch-limited origin at time zero.
    Hold evidence must show the requested intervention even when mandatory
    waiting makes the paired departure and boarding outcomes identical.
    """
    component = TrainComponent(
        [
            Train(
                "A",
                2,
                (ScheduledStop("S", "P", 0, 0),),
                line_id="green",
                onboard_load=1,
            )
        ],
        decision=DecisionPipeline(FixedHold(hold_s)),
        passenger_queue=PlatformQueue(("P",)),
        suspensions=suspensions,
    )
    scheduler = Scheduler()
    component.start(scheduler)
    scheduler.schedule(
        PassengerArrival(
            time_s=walker_s, passenger_id="walker", group_id="burst", platform_id="P"
        )
    )
    events: list[Event] = []

    def process(event: Event) -> None:
        events.append(event)
        component.handle(event, scheduler)

    scheduler.run_until(100, process)
    # An absorbed hold leaves departure/boarding unchanged, so prove it was applied.
    holds = [event for event in events if isinstance(event, Hold)]
    if hold_s > 0:
        [hold] = holds
        assert hold.requested_s == hold_s
        assert hold.applied_s == hold_s
    else:
        assert holds == []
    [departure] = [event for event in events if isinstance(event, TrainDeparture)]
    boarded = any(isinstance(event, Boarding) for event in events)
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
