# AI contribution: 50% or more AI-generated
"""Strategy decisions inside full runs (US-2.1 #38, #39, US-2.3 #46)."""

import json
from types import SimpleNamespace

import pytest

from simulator.control.decision import DecisionPipeline, HoldDecision
from simulator.control.interface import DecisionController, HoldAction
from simulator.control.prediction_error import (
    PredictionErrorModel,
    PredictionErrorSettings,
)
from simulator.engine.random_streams import StreamManager
from simulator.engine.runner import run_scenario
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


class HoldEveryTrain(DecisionController):
    """Asks for a fixed hold on whichever train is deciding."""

    name = "hold_every_train"

    def __init__(self, train_id=None, duration_s=30.0):
        self.train_id = train_id
        self.duration_s = duration_s

    def evaluate(self, observation):
        train_id = self.train_id or observation.train_id
        return (HoldAction(train_id, self.duration_s, "test hold"),)


class RefuseAll:
    """Stand-in for the rule checking layer (#57) that refuses every hold."""

    def validate(self, action, observation):
        return HoldDecision(action.duration_s, 0.0, "refused: test rule")


def make_trains():
    # A visits P1 (100-130) then P2 (200-230); B visits P1 (400-430)
    return [
        Train(
            id="A",
            capacity=800,
            schedule=(
                ScheduledStop("S1", "P1", 100, 130),
                ScheduledStop("S2", "P2", 200, 230),
            ),
        ),
        Train(id="B", capacity=800, schedule=(ScheduledStop("S1", "P1", 400, 430),)),
    ]


def run(tmp_path, decision=None):
    scenario = SimpleNamespace(master_seed=7, duration_s=1000.0)
    result = run_scenario(
        scenario,
        lambda seed: None,
        lambda _scenario, _streams: [TrainComponent(make_trains(), decision=decision)],
        tmp_path,
    )
    text = result.events_path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def of_type(records, event_type):
    return [record for record in records if record["event_type"] == event_type]


def test_no_control_run_has_no_holds(tmp_path):
    records = run(tmp_path)
    departures = of_type(records, "train_departure")
    assert of_type(records, "hold") == []
    assert len(departures) == 3
    assert {record["hold_s"] for record in departures} == {0.0}


def test_requested_hold_delays_departure_until_hold_end(tmp_path):
    records = run(tmp_path, DecisionPipeline(HoldEveryTrain()))
    first_hold = of_type(records, "hold")[0]
    assert (first_hold["time_s"], first_hold["requested_s"]) == (130.0, 30.0)
    assert first_hold["applied_s"] == 30.0
    assert of_type(records, "hold_end")[0]["time_s"] == 160.0
    departure = of_type(records, "train_departure")[0]
    assert (departure["time_s"], departure["hold_s"]) == (160.0, 30.0)


def test_refused_hold_is_recorded_and_train_leaves_on_time(tmp_path):
    decision = DecisionPipeline(HoldEveryTrain(), enforcer=RefuseAll())
    records = run(tmp_path, decision)
    first_hold = of_type(records, "hold")[0]
    assert (first_hold["applied_s"], first_hold["reason"]) == (
        0.0,
        "refused: test rule",
    )
    assert of_type(records, "hold_end") == []
    departure = of_type(records, "train_departure")[0]
    assert (departure["time_s"], departure["hold_s"]) == (130.0, 0.0)


def test_strategy_cannot_hold_a_different_train(tmp_path):
    decision = DecisionPipeline(HoldEveryTrain(train_id="B"))
    with pytest.raises(ValueError, match="may only hold A"):
        run(tmp_path, decision)


def test_held_runs_are_reproducible(tmp_path):
    first = run(tmp_path / "first", DecisionPipeline(HoldEveryTrain()))
    second = run(tmp_path / "second", DecisionPipeline(HoldEveryTrain()))
    assert first == second


class SeenBy:
    """Records the snapshot each side received: strategy (seen) or rules (truth)."""

    name = "seen_by"

    def __init__(self):
        self.seen, self.truth = [], []

    def evaluate(self, observation):
        self.seen.append(observation)
        return (HoldAction(observation.train_id, 30.0, "test hold"),)

    def validate(self, action, observation):
        self.truth.append(observation)
        return HoldDecision(action.duration_s, action.duration_s, action.reason)


def run_with_error(tmp_path, settings):
    recorder = SeenBy()
    stream = StreamManager(7).get_stream("prediction_errors")
    model = PredictionErrorModel(settings, stream)
    run(tmp_path, DecisionPipeline(recorder, enforcer=recorder, error_model=model))
    return recorder


def test_strategy_sees_estimates_while_rules_see_truth(tmp_path):
    # At A's first decision (130 s), B is truly due at P1 at 400 s
    recorder = run_with_error(tmp_path, PredictionErrorSettings())
    truth_b = recorder.truth[0].trains[1]
    seen_b = recorder.seen[0].trains[1]
    assert truth_b.predicted_arrival_s == 400.0
    assert seen_b.predicted_arrival_s != 400.0
    assert seen_b.delay_s == truth_b.delay_s


def test_perfect_information_strategy_sees_true_values(tmp_path):
    recorder = run_with_error(tmp_path, PredictionErrorSettings(0, 0, 0))
    assert len(recorder.seen) == 3
    assert recorder.seen == recorder.truth
