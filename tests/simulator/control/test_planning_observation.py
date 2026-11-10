# AI contribution: 50% or more AI-generated
"""Forward snapshots include returns, existing holds and prediction errors (#61)."""

from dataclasses import FrozenInstanceError, replace

import pytest

from simulator.control.decision import DecisionPipeline
from simulator.control.interface import DecisionController, HoldAction
from simulator.control.prediction_error import (
    PredictionErrorModel,
    PredictionErrorSettings,
)
from simulator.engine.event_queue import Scheduler
from simulator.engine.random_streams import StreamManager
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent
from tests.simulator.control.rolling_helpers import snapshot


def test_remaining_visits_include_return_recovery_and_skip_terminal_departure():
    train = Train(
        "A",
        800,
        (ScheduledStop("S1", "P1", 90, 100), ScheduledStop("S2", "P2", 200, 210)),
        current_delay=40,
        generated_delay_s=40,
        layover_slack=60,
        return_trips=((ScheduledStop("S2", "R", 300, 310),),),
    )
    component = TrainComponent([train])
    visits = component.future_visits(0)
    assert [(v.arrival_s, v.departure_s) for v in visits] == [
        (130, 140),
        (240, 240),
        (300, 310),
    ]
    assert visits[1].skips_departure is True
    assert visits[1].can_hold is False
    assert visits[2].recovery_s == 20
    assert [v.key for v in visits] == [("A", 0, 0), ("A", 0, 1), ("A", 1, 0)]
    with pytest.raises(FrozenInstanceError):
        visits[0].arrival_s = 1


class HoldFirst(DecisionController):
    name = "hold_first"

    def evaluate(self, observation):
        if observation.platform_id == "P1":
            return (HoldAction("A", 10, "fixture"),)
        return ()


def test_existing_hold_is_fixed_and_carried_into_following_visits():
    train = Train(
        "A",
        800,
        (ScheduledStop("S1", "P1", 90, 100), ScheduledStop("S2", "P2", 200, 210)),
    )
    component = TrainComponent([train], decision=DecisionPipeline(HoldFirst()))
    scheduler = Scheduler()
    component.start(scheduler)
    scheduler.run_until(105, lambda event: component.handle(event, scheduler))
    first, second = component.future_visits(105)
    assert first.can_hold is False
    assert first.departure_s == 110
    assert second.arrival_s == 210
    assert second.departure_s == 220


def test_future_times_receive_prediction_error_without_changing_dwell():
    seen = snapshot()
    model = PredictionErrorModel(
        PredictionErrorSettings(), StreamManager(7).get_stream("prediction_errors")
    )
    estimated = model.apply(seen)
    future = estimated.future_visits[1]
    assert future.arrival_s != seen.future_visits[1].arrival_s
    assert future.departure_s - future.arrival_s == pytest.approx(10, abs=1e-10)
    assert estimated.future_visits[0] == seen.future_visits[0]


def test_perfect_information_keeps_complete_future_view_unchanged():
    seen = snapshot()
    model = PredictionErrorModel(
        PredictionErrorSettings(0, 0, 0),
        StreamManager(7).get_stream("prediction_errors"),
    )
    assert model.apply(seen) == seen


def test_future_visits_require_immutable_tuple():
    seen = snapshot()
    with pytest.raises(ValueError, match="future_visits must be a tuple"):
        replace(seen, future_visits=[])
