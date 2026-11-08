# AI contribution: 50% or more AI-generated
"""Prediction errors across paired runs with the same seed (section 9, #191).

Common random numbers need the same prediction to get the same error in both
runs of a pair. The error model draws in decision order from one stream, so a
hold that changes later snapshots shifts every later error. The second test
documents that drift until keyed draws (#191) replace the sequential stream.
"""

from types import SimpleNamespace

import pytest

from simulator.control.decision import DecisionPipeline
from simulator.control.interface import DecisionController, HoldAction
from simulator.control.prediction_error import (
    PredictionErrorModel,
    PredictionErrorSettings,
    arrival_sigma_s,
)
from simulator.engine.random_streams import StreamManager
from simulator.engine.runner import run_scenario
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent

SEED = 7
HOLD_S = 120.0


class HoldTrainA(DecisionController):
    """Holds train A for a fixed time at each of its stops; no other train."""

    name = "hold_train_a"

    def __init__(self, hold_s):
        self.hold_s = hold_s

    def evaluate(self, observation):
        """Return a hold for train A only; every other train leaves on time."""
        if self.hold_s and observation.train_id == "A":
            return (HoldAction("A", self.hold_s, "test hold"),)
        return ()


class RecordingModel(PredictionErrorModel):
    """The real model, also keeping each arrival error by the prediction it is for."""

    def __init__(self, stream):
        super().__init__(PredictionErrorSettings(), stream)
        self.errors = {}
        self._decisions = {}

    def apply(self, truth):
        seen = super().apply(truth)
        # The nth decision of a train at a platform is the same decision in both runs
        place = (truth.train_id, truth.platform_id)
        self._decisions[place] = self._decisions.get(place, 0) + 1
        for true_train, seen_train in zip(truth.trains, seen.trains, strict=True):
            if true_train.predicted_arrival_s is None:
                continue
            horizon_s = true_train.predicted_arrival_s - truth.time_s
            error_s = seen_train.predicted_arrival_s - true_train.predicted_arrival_s
            # Dividing by sigma leaves the random draw, so a hold that changes the
            # horizon does not count as a different error
            key = (*place, self._decisions[place], true_train.train_id)
            self.errors[key] = error_s / arrival_sigma_s(horizon_s)
        return seen


def make_trains():
    # Four trains 150 s apart, each calling at three stops 200 s apart
    return [
        Train(
            name,
            800,
            tuple(
                ScheduledStop(f"S{k}", f"P{k}", start + 200 * k, start + 200 * k + 30)
                for k in range(3)
            ),
        )
        for name, start in zip("ABCD", range(100, 700, 150), strict=True)
    ]


def arrival_errors(output_dir, hold_s):
    """Run the scenario with the given hold on train A; return its arrival errors."""
    model = RecordingModel(StreamManager(SEED).get_stream("prediction_errors"))
    decision = DecisionPipeline(HoldTrainA(hold_s), error_model=model)
    # Each run needs its own folder: the runner refuses one that holds output
    run_scenario(
        SimpleNamespace(master_seed=SEED, duration_s=2000.0),
        lambda _seed: None,
        lambda _scenario, _streams: [TrainComponent(make_trains(), decision=decision)],
        output_dir,
    )
    return model.errors


def test_held_run_makes_every_prediction_of_the_plain_run(tmp_path):
    # Guards the pairing below: the hold changes the run, but every arrival
    # prediction from the run without holds still happens, so errors can be
    # compared one to one
    plain = arrival_errors(tmp_path / "plain", 0)
    held = arrival_errors(tmp_path / "held", HOLD_S)
    assert len(plain) > 10
    assert plain.keys() <= held.keys()


# Strict: once keyed draws make this pass, the run fails until the marker goes
@pytest.mark.xfail(
    strict=True,
    reason="errors are drawn in decision order; keyed draws are planned in #191",
)
def test_same_prediction_gets_same_error_in_paired_runs(tmp_path):
    # Same seed, so section 9 expects the same error for the same prediction
    plain = arrival_errors(tmp_path / "plain", 0)
    held = arrival_errors(tmp_path / "held", HOLD_S)
    assert {key: held[key] for key in plain} == pytest.approx(plain)
