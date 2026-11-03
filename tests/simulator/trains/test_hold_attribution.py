# AI contribution: 50% or more AI-generated
"""Test hold and disruption delay through train events (US-2.3 #48).

Recovery follows Mathematical Foundations (Section 6). All times are seconds.
"""

from collections.abc import Sequence

import pytest

from simulator.control.decision import DecisionPipeline
from simulator.control.interface import (
    DecisionController,
    HoldAction,
    ObservationSnapshot,
)
from simulator.control.rules import OperatingRulesEnforcer
from simulator.control.settings import OperatingRulesConfig
from simulator.control.strategies.no_control import NoControlStrategy
from simulator.engine.event_queue import Scheduler
from simulator.engine.events import Event, Hold, HoldEnd, TrainArrival, TrainDeparture
from simulator.trains.disruption import DelayInjection
from simulator.trains.suspension import LineSuspension
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


class FixedPlatformHolds(DecisionController):
    """Hold one train for a set time at each chosen platform."""

    name = "fixed_platform_holds"

    def __init__(self, train_id: str, holds: dict[str, float]) -> None:
        """Store hold times in seconds by platform."""
        self.train_id = train_id
        self.holds = holds

    def evaluate(self, observation: ObservationSnapshot) -> tuple[HoldAction, ...]:
        """Request a hold for the chosen train and platform."""
        duration_s = self.holds.get(observation.platform_id)
        if observation.train_id != self.train_id or duration_s is None:
            return ()
        return (HoldAction(observation.train_id, duration_s, self.name),)


def run_held_train(
    train: Train,
    duration_s: float | dict[str, float],
    *,
    suspensions: Sequence[LineSuspension] = (),
    injections: Sequence[DelayInjection] = (),
    max_hold_s: float = 300,
    rule_action: str = "CLAMP",
    other_trains: Sequence[Train] = (),
    gap_s: float = 90,
) -> list[Event]:
    """Run the train with holds and operating rules; return its events."""
    holds = duration_s if isinstance(duration_s, dict) else {"P1": duration_s}
    strategy = (
        FixedPlatformHolds(train.id, holds) if duration_s else NoControlStrategy()
    )
    rules = OperatingRulesConfig(
        max_hold_time=max_hold_s, rule_action_map={"max_hold_exceeded": rule_action}
    )
    pipeline = DecisionPipeline(
        strategy,
        enforcer=OperatingRulesEnforcer(rules),
    )
    component = TrainComponent(
        [*other_trains, train],
        minimum_gap_s=gap_s,
        decision=pipeline,
        suspensions=suspensions,
        delay_injections=injections,
    )
    scheduler = Scheduler()
    component.start(scheduler)
    events: list[Event] = []

    def process(event: Event) -> None:
        events.append(event)
        component.handle(event, scheduler)

    scheduler.run_until(2000, process)
    return events


def ordinary_train() -> Train:
    """Create a train with 30-second stops and 220 seconds of travel."""
    return Train(
        "A",
        100,
        (ScheduledStop("S1", "P1", 250, 280), ScheduledStop("S2", "P2", 500, 530)),
        line_id="green",
    )


def test_on_time_hold_does_not_become_disruption_at_following_stop():
    """A 120-second hold stays hold delay at the next stop."""
    events = run_held_train(ordinary_train(), 120)
    holds = [event for event in events if isinstance(event, Hold)]
    hold_ends = [event for event in events if isinstance(event, HoldEnd)]
    departures = [event for event in events if isinstance(event, TrainDeparture)]
    arrivals = [event for event in events if isinstance(event, TrainArrival)]

    assert [(event.time_s, event.requested_s, event.applied_s) for event in holds] == [
        (280, 120, 120)
    ]
    assert [event.time_s for event in hold_ends] == [400]
    assert [event.time_s for event in departures] == [400, 650]
    assert [event.hold_s for event in departures] == [120, 0]
    assert [event.generated_delay_s for event in departures] == [120, 120]
    assert [event.inherited_delay_s for event in departures] == [0, 0]
    assert [event.disruption_delay_s for event in departures] == [0, 0]
    # Next arrival: 400 + 220 = 620, with no disruption delay.
    assert [event.time_s for event in arrivals] == [250, 620]
    assert [event.disruption_delay_s for event in arrivals] == [0, 0]


@pytest.mark.parametrize(
    ("hold_s", "departures_s", "lateness_s"),
    [(10, [130, 230], 0), (30, [150, 250], 20)],
    ids=["hold_only_absorbs_earliness", "hold_exceeds_earliness"],
)
def test_early_train_records_full_hold_but_only_remaining_lateness(
    hold_s, departures_s, lateness_s
):
    """The first 10 seconds of holding use up the train's earliness."""
    train = Train(
        "early",
        100,
        (ScheduledStop("S1", "P1", 100, 130), ScheduledStop("S2", "P2", 200, 230)),
        line_id="green",
        current_delay=-10,
    )
    events = run_held_train(train, hold_s)
    departures = [event for event in events if isinstance(event, TrainDeparture)]
    arrivals = [event for event in events if isinstance(event, TrainArrival)]

    assert [event.time_s for event in departures] == departures_s
    assert [event.hold_s for event in departures] == [hold_s, 0]
    assert [event.generated_delay_s for event in departures] == [lateness_s, lateness_s]
    assert [event.disruption_delay_s for event in departures] == [0, 0]
    assert [event.disruption_delay_s for event in arrivals] == [0, 0]


@pytest.mark.parametrize(
    ("start_s", "end_s", "departure_s", "unheld_departure_s", "disruption_s"),
    [(250, 450, 450, 450, 170), (250, 350, 400, 350, 70), (300, 450, 450, 280, 0)],
    ids=[
        "suspension_outlasts_hold",
        "hold_outlasts_suspension",
        "hold_enters_suspension",
    ],
)
def test_overlapping_suspension_attributes_only_the_no_hold_dispatch_wait(
    start_s, end_s, departure_s, unheld_departure_s, disruption_s
):
    """Count only suspension delay that would occur without holding.

    The train is ready at 280, so a suspension starting at 300 adds no such delay.
    """
    suspension = LineSuspension("green", start_s, end_s)
    unheld_events = run_held_train(ordinary_train(), 0, suspensions=[suspension])
    unheld_departures = [
        event for event in unheld_events if isinstance(event, TrainDeparture)
    ]
    events = run_held_train(ordinary_train(), 120, suspensions=[suspension])
    departures = [event for event in events if isinstance(event, TrainDeparture)]
    arrivals = [event for event in events if isinstance(event, TrainArrival)]
    first, following = departures

    assert unheld_departures[0].time_s == unheld_departure_s
    assert first.time_s == departure_s
    assert first.hold_s == 120
    assert first.generated_delay_s == departure_s - 280
    assert first.disruption_delay_s == disruption_s
    assert following.hold_s == 0
    assert following.disruption_delay_s == disruption_s
    assert arrivals[1].disruption_delay_s == disruption_s


def test_injected_delay_stays_separate_from_a_later_hold():
    """60 seconds of disruption plus a 120-second hold means 180 seconds late."""
    disruption = DelayInjection("arrival-delay", 0, 60, "P1", train_id="A")
    events = run_held_train(ordinary_train(), 120, injections=[disruption])
    departures = [event for event in events if isinstance(event, TrainDeparture)]
    arrivals = [event for event in events if isinstance(event, TrainArrival)]

    assert [event.time_s for event in arrivals] == [310, 680]
    assert [event.disruption_delay_s for event in arrivals] == [60, 60]
    assert [event.time_s for event in departures] == [460, 710]
    assert [event.hold_s for event in departures] == [120, 0]
    assert [event.generated_delay_s for event in departures] == [180, 180]
    assert [event.disruption_delay_s for event in departures] == [60, 60]


def test_terminal_slack_recovers_hold_and_disruption_in_the_same_proportion():
    """90 seconds of recovery halves both hold and disruption delay."""
    train = Train(
        "A",
        100,
        (ScheduledStop("S1", "P1", 250, 280), ScheduledStop("S2", "P2", 500, 500)),
        line_id="green",
        layover_slack=90,
        return_trips=((ScheduledStop("S2", "P3", 600, 600),),),
    )
    disruption = DelayInjection("arrival-delay", 0, 60, "P1", train_id="A")
    events = run_held_train(train, 120, injections=[disruption])
    arrivals = [event for event in events if isinstance(event, TrainArrival)]
    departures = [event for event in events if isinstance(event, TrainDeparture)]

    assert [event.time_s for event in arrivals] == [310, 680, 690]
    # Recover half of 180 seconds: disruption drops from 60 to 30.
    assert [event.disruption_delay_s for event in arrivals] == [60, 60, 30]
    assert [event.platform_id for event in departures] == ["P1", "P3"]
    assert [event.time_s for event in departures] == [460, 690]
    assert [event.hold_s for event in departures] == [120, 0]
    assert [event.generated_delay_s for event in departures] == [180, 90]
    assert [event.inherited_delay_s for event in departures] == [0, 0]
    assert [event.disruption_delay_s for event in departures] == [60, 30]


@pytest.mark.parametrize(
    ("rule_action", "applied_s", "departure_times"),
    [("CLAMP", 60, [340, 590]), ("REFUSE", 0, [280, 530])],
)
def test_hold_attribution_uses_applied_duration_after_operating_rules(
    rule_action, applied_s, departure_times
):
    """Count only the hold time allowed by the operating rules."""
    events = run_held_train(
        ordinary_train(), 120, max_hold_s=60, rule_action=rule_action
    )
    holds = [event for event in events if isinstance(event, Hold)]
    hold_ends = [event for event in events if isinstance(event, HoldEnd)]
    departures = [event for event in events if isinstance(event, TrainDeparture)]

    assert [(event.requested_s, event.applied_s) for event in holds] == [
        (120, applied_s)
    ]
    assert [event.time_s for event in hold_ends] == ([340] if applied_s else [])
    assert [event.time_s for event in departures] == departure_times
    assert [event.hold_s for event in departures] == [applied_s, 0]
    assert [event.generated_delay_s for event in departures] == [applied_s, applied_s]
    assert [event.disruption_delay_s for event in departures] == [0, 0]


@pytest.mark.parametrize(
    ("scheduled_s", "hold_s", "departure_s", "generated_s", "inherited_s"),
    [(50, 30, 190, 0, 140), (50, 120, 220, 30, 140), (200, 120, 220, 20, 0)],
    ids=[
        "clearance_dominates_hold",
        "hold_exceeds_clearance",
        "earliness_absorbs_wait",
    ],
)
def test_hold_and_minimum_gap_keep_own_and_inherited_lateness_separate(
    scheduled_s, hold_s, departure_s, generated_s, inherited_s
):
    """The leader leaves at 100; the follower must wait until 190.

    A hold ending at 220 adds 30 seconds beyond clearance, but only 20 seconds
    of lateness when departure is scheduled at 200.
    """
    leader = Train("leader", 100, (ScheduledStop("S1", "P1", 0, 100),))
    train = Train(
        "follower",
        100,
        (ScheduledStop("S1", "P1", scheduled_s, scheduled_s),),
        current_delay=-100 if scheduled_s == 200 else 0,
    )
    events = run_held_train(train, hold_s, other_trains=[leader])
    departure = next(
        event
        for event in events
        if isinstance(event, TrainDeparture) and event.train_id == "follower"
    )

    # Allow 1e-12 for rounding just after the platform clears at 100.
    assert departure.time_s == pytest.approx(departure_s, rel=0, abs=1e-12)
    assert departure.hold_s == hold_s
    assert departure.generated_delay_s == pytest.approx(generated_s, rel=0, abs=1e-12)
    assert departure.inherited_delay_s == pytest.approx(inherited_s, rel=0, abs=1e-12)
    assert departure.disruption_delay_s == pytest.approx(0, rel=0, abs=1e-12)


def test_fractional_readiness_on_suspension_start_keeps_original_boundary():
    """Rounding must not move readiness before the suspension starts at 0.1."""
    train = Train(
        "fractional",
        100,
        (ScheduledStop("S1", "P1", 0.1, 0.1),),
        line_id="green",
    )
    suspension = LineSuspension("green", 0.1, 0.8)
    events = run_held_train(train, 0.6, suspensions=[suspension])
    departure = next(event for event in events if isinstance(event, TrainDeparture))

    assert departure.time_s == 0.8
    assert departure.hold_s == 0.6
    assert departure.disruption_delay_s == pytest.approx(0.7, rel=0, abs=1e-15)
    assert departure.generated_delay_s == pytest.approx(0.7, rel=0, abs=1e-15)


def test_repeated_holds_add_own_lateness_without_reclassifying_disruption():
    """Two holds add 180 seconds; disruption stays at 60 seconds."""
    disruption = DelayInjection("arrival-delay", 0, 60, "P1", train_id="A")
    events = run_held_train(
        ordinary_train(), {"P1": 120, "P2": 60}, injections=[disruption]
    )
    departures = [event for event in events if isinstance(event, TrainDeparture)]

    assert [event.time_s for event in departures] == [460, 770]
    assert [event.hold_s for event in departures] == [120, 60]
    assert [event.generated_delay_s for event in departures] == [180, 240]
    assert [event.disruption_delay_s for event in departures] == [60, 60]
