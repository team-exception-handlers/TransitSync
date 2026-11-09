# AI contribution: 50% or more AI-generated
"""Merged irregularity/planning views and bounded headway metadata (#61, #63)."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import pytest

from simulator.control.decision import DecisionPipeline
from simulator.control.interface import ObservationSnapshot
from simulator.control.planning import RollingHorizonSettings
from simulator.control.prediction_error import (
    PredictionErrorModel,
    PredictionErrorSettings,
)
from simulator.control.settings import parse_control_settings
from simulator.engine.event_queue import Scheduler
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent
from tests.simulator.control.test_prediction_error import FixedDraws


class Probe:
    name = "stack_probe"
    requires_future_visits = True

    def __init__(self):
        self.planner = SimpleNamespace(settings=RollingHorizonSettings())
        self.seen = []

    def evaluate(self, seen):
        self.seen.append(seen)
        return ()


def bounded_snapshot():
    probe = Probe()
    trains = [
        Train(
            name,
            800,
            (
                ScheduledStop("S1", "P1", start, start + 10),
                ScheduledStop("S2", "P2", start + 110, start + 120),
            ),
        )
        for name, start in (("A", 90), ("B", 1100))
    ]
    component = TrainComponent(trains, decision=DecisionPipeline(probe))
    scheduler = Scheduler()
    component.start(scheduler)
    scheduler.run_until(100, lambda event: component.handle(event, scheduler))
    return component, scheduler, probe.seen[0]


def test_bounded_planning_keeps_later_services_separate_and_detached():
    component, scheduler, seen = bounded_snapshot()
    assert [v.arrival_s for v in seen.future_visits] == [90, 200]
    assert [v.departure_s for v in seen.headway_visits] == [1110, 1220]
    assert seen.service_irregularity is None
    before = deepcopy((component.trains, scheduler.now, scheduler.pending))
    assert (
        component.headway_visits(100, 400, frozenset({"P1", "P2"}))
        == seen.headway_visits
    )
    assert (component.trains, scheduler.now, scheduler.pending) == before
    scheduler.run_until(1300, lambda event: component.handle(event, scheduler))
    assert [v.departure_s for v in seen.headway_visits] == [1110, 1220]
    with pytest.raises(FrozenInstanceError):
        seen.headway_visits[0].departure_s = 0


def test_headway_collection_requires_immutable_tuple():
    _, _, seen = bounded_snapshot()
    with pytest.raises(ValueError, match="headway_visits must be a tuple"):
        replace(seen, headway_visits=[])


def test_headway_references_reuse_train_error_and_preserve_dwell():
    _, _, seen = bounded_snapshot()
    draws = FixedDraws(0, 0.5, 0, 0.5)
    model = PredictionErrorModel(PredictionErrorSettings(), draws)
    estimated = model.apply(seen)
    assert (
        estimated.trains[1].predicted_arrival_s == estimated.headway_visits[0].arrival_s
    )
    assert estimated.headway_visits[0].arrival_s != seen.headway_visits[0].arrival_s
    assert estimated.headway_visits[0].departure_s - estimated.headway_visits[
        0
    ].arrival_s == pytest.approx(10, abs=1e-10)
    assert draws.values == []


def test_main_positional_irregularity_argument_remains_compatible():
    seen = ObservationSnapshot(0, "A", "S", "P", 0, (), (), (), 0.5)
    assert seen.service_irregularity == 0.5
    assert seen.future_visits == ()


def test_real_irregularity_measurements_coexist_with_planning_data():
    probe = Probe()
    trains = [
        Train(
            str(i),
            800,
            (ScheduledStop("S", "P", t - 10, t),),
            current_delay=delay,
            generated_delay_s=delay,
        )
        for i, (t, delay) in enumerate(((100, 0), (160, 0), (220, 30), (310, 0)))
    ]
    component = TrainComponent(
        trains,
        minimum_gap_s=60,
        decision=DecisionPipeline(probe),
        control=parse_control_settings({"irregularity_window_size": 1}),
    )
    scheduler = Scheduler()
    component.start(scheduler)
    scheduler.run_until(400, lambda event: component.handle(event, scheduler))
    assert [s.service_irregularity for s in probe.seen] == [None, None, 0, 0.5]
    assert all(s.future_visits for s in probe.seen)


def test_headway_lookup_stops_when_requested_platforms_cannot_recur(monkeypatch):
    trains = [
        Train(
            str(i),
            800,
            tuple(
                ScheduledStop("S", f"P{i}-{j}", 100 + j * 1000, 110 + j * 1000)
                for j in range(91)
            ),
        )
        for i in range(30)
    ]
    component = TrainComponent(trains)
    visited = []
    original = component._future_visit

    def record(key, *args):
        visited.append(key)
        return original(key, *args)

    monkeypatch.setattr(component, "_future_visit", record)
    references = component.headway_visits(
        0, 300, frozenset(f"P{i}-0" for i in range(30))
    )
    assert references == ()
    assert len(visited) == 30


def test_headway_lookup_includes_return_recovery_without_mutating_train():
    train = Train(
        "A",
        800,
        (ScheduledStop("S1", "P1", 90, 100), ScheduledStop("S2", "T", 200, 210)),
        current_delay=40,
        generated_delay_s=40,
        layover_slack=60,
        return_trips=((ScheduledStop("S2", "P1", 300, 310),),),
    )
    references = TrainComponent([train]).headway_visits(0, 200, frozenset({"P1"}))
    assert [v.departure_s for v in references] == [310]
    assert references[0].recovery_s == 20
    assert train.current_delay == 40
    assert train.current_trip_index == 0


def test_headway_lookup_skips_platforms_already_passed(monkeypatch):
    train = Train(
        "A",
        800,
        (ScheduledStop("S1", "P1", 90, 100), ScheduledStop("S2", "P2", 1000, 1010)),
    )
    component = TrainComponent([train])
    scheduler = Scheduler()
    component.start(scheduler)
    scheduler.run_until(100, lambda event: component.handle(event, scheduler))

    def unexpected(*args):
        pytest.fail("lookahead scanned a route that cannot revisit this platform")

    monkeypatch.setattr(component, "_future_visit", unexpected)
    assert component.headway_visits(100, 400, frozenset({"P1"})) == ()
