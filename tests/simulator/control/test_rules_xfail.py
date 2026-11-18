"""Spike #195: Verify that post-run validation detects unsafe hold decisions."""

import json
from types import SimpleNamespace

import pytest

from simulator.control.decision import DecisionPipeline, PassThroughEnforcer
from simulator.control.interface import DecisionController, HoldAction
from simulator.control.validation import (
    PostRunValidationFailedError,
    validate_run_results,
)
from simulator.engine.runner import run_scenario
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent

MAX_HOLD_S = 300.0
REQUESTED_HOLD_S = 999.0


class HoldEveryTrain(DecisionController):
    """Request the same hold whenever a train reaches its decision point."""

    name = "spike_195_hold_every_train"

    def evaluate(self, observation):
        return (
            HoldAction(
                observation.train_id,
                REQUESTED_HOLD_S,
                "Spike #195 runtime verification test",
            ),
        )


def test_post_run_validation_detects_hold_exceeding_operating_rule(tmp_path):
    """A 999-second applied hold should be caught by post-run validation.

    The pass-through enforcer deliberately allows the unsafe hold so this
    test can check whether post-run validation independently detects it.
    """
    scenario = SimpleNamespace(master_seed=42, duration_s=500.0)
    train = Train(
        id="A",
        capacity=800,
        schedule=(ScheduledStop("S1", "P1", 100, 130),),
    )
    decision = DecisionPipeline(
        HoldEveryTrain(),
        enforcer=PassThroughEnforcer(),
    )
    component = TrainComponent([train], decision=decision)
    result = run_scenario(
        scenario,
        lambda seed: None,
        lambda _scenario, _streams: [component],
        tmp_path,
    )

    # Confirm the simulation actually recorded the unsafe hold.
    events = [
        json.loads(line)
        for line in result.events_path.read_text(encoding="utf-8").splitlines()
    ]
    holds = [event for event in events if event["event_type"] == "hold"]
    assert len(holds) == 1
    assert holds[0]["requested_s"] == REQUESTED_HOLD_S
    assert holds[0]["applied_s"] == REQUESTED_HOLD_S
    assert holds[0]["applied_s"] > MAX_HOLD_S

    # Post-run validation now independently detects and raises on the violation.
    with pytest.raises(PostRunValidationFailedError):
        validate_run_results(result)
