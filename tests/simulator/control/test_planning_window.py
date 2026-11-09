# AI contribution: 50% or more AI-generated
"""Bound observation work before copying or perturbing full-day routes (#61)."""

from types import SimpleNamespace

import pytest

from simulator.control.decision import DecisionPipeline
from simulator.control.observation_builder import ObservationBuilder
from simulator.control.planning import RollingHorizonSettings
from simulator.engine.event_queue import Scheduler
from simulator.engine.events import DepartureDue
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


def returning_component():
    """40 s lateness consumes 40 of 60 s slack before the 300 s return."""
    return TrainComponent(
        [
            Train(
                "A",
                800,
                (
                    ScheduledStop("S1", "P1", 90, 100),
                    ScheduledStop("S2", "P2", 200, 210),
                ),
                current_delay=40,
                generated_delay_s=40,
                layover_slack=60,
                return_trips=((ScheduledStop("S2", "R", 300, 310),),),
            )
        ]
    )


@pytest.mark.parametrize("cutoff, count", [(129, 0), (130, 1), (299, 2), (300, 3)])
def test_cutoff_includes_exact_arrival_and_preserves_return_recovery(cutoff, count):
    component = returning_component()
    complete = component.future_visits(0)
    bounded = component.future_visits(0, cutoff)
    assert bounded == complete[:count]
    assert component.trains["A"].current_delay == 40


def test_bounded_copy_stops_before_visiting_later_trips(monkeypatch):
    component = returning_component()
    visited = []
    original = component._future_visit

    def record(key, *args):
        visited.append(key)
        return original(key, *args)

    monkeypatch.setattr(component, "_future_visit", record)
    assert len(component.future_visits(0, 130)) == 1
    # Only the included visit and the first excluded visit are projected.
    assert visited == [("A", 0, 0), ("A", 0, 1)]


def test_long_routes_stop_per_train_instead_of_copying_whole_day(monkeypatch):
    trains = [
        Train(
            str(i),
            800,
            tuple(
                ScheduledStop(f"S{j}", f"P{i}-{j}", 100 + j * 1000, 110 + j * 1000)
                for j in range(91)
            ),
        )
        for i in range(30)
    ]
    component = TrainComponent(trains)
    projected = []
    original = component._future_visit

    def record(key, *args):
        projected.append(key)
        return original(key, *args)

    monkeypatch.setattr(component, "_future_visit", record)
    assert len(component.future_visits(0, 300)) == 30
    assert len(projected) == 60


class PlanningProbe:
    """Match the downstream adapter's planner.settings configuration interface."""

    name = "planning_probe"
    requires_future_visits = True

    def __init__(self, window_s):
        if window_s is not None:
            self.planner = SimpleNamespace(settings=RollingHorizonSettings(window_s))
        self.seen = None

    def evaluate(self, observation):
        self.seen = observation
        return ()


@pytest.mark.parametrize("window, count", [(None, 2), (99, 0), (100, 1), (160, 2)])
def test_pipeline_passes_configured_window_to_observation_source(window, count):
    component = returning_component()
    scheduler = Scheduler()
    component.start(scheduler)
    scheduler.run_until(140, lambda event: component.handle(event, scheduler))
    probe = PlanningProbe(window)
    decision = DepartureDue(
        time_s=140, train_id="A", station_id="S1", platform_id="P1", scheduled_s=100
    )
    DecisionPipeline(probe).decide(decision, component)
    assert len(probe.seen.future_visits) == count


def test_bounded_view_retains_current_dwelling_visit():
    component = returning_component()
    scheduler = Scheduler()
    component.start(scheduler)
    scheduler.run_until(135, lambda event: component.handle(event, scheduler))
    visits = component.future_visits(135, 135)
    assert len(visits) == 1
    assert visits[0].arrived is True
    assert visits[0].departure_s == 140


def test_nonplanning_builder_does_not_request_future_visits(monkeypatch):
    component = returning_component()

    def unexpected(*args):
        pytest.fail("nonplanning controller requested a forward snapshot")

    monkeypatch.setattr(component, "future_visits", unexpected)
    decision = DepartureDue(
        time_s=0, train_id="A", station_id="S1", platform_id="P1", scheduled_s=100
    )
    assert ObservationBuilder().build(decision, component).future_visits == ()
