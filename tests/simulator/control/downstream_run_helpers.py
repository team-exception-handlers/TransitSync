# AI contribution: 50% or more AI-generated
"""Event-engine probes shared by forecast and coordinated-run tests."""

import json
from types import SimpleNamespace

from simulator.control.decision import DecisionPipeline
from simulator.control.interface import DecisionController, HoldAction
from simulator.control.planning import RollingHorizonSettings
from simulator.engine.runner import run_scenario
from simulator.trains.train_component import TrainComponent


class CaptureHold(DecisionController):
    """Capture one true forward view, then force the tested current hold."""

    name = "capture_hold"
    requires_future_visits = True

    def __init__(self, hold):
        self.hold = hold
        self.observation = None
        # These engine comparisons cover complete routes over the 1000 s run.
        # Request that window explicitly when the bounded #196 builder is used.
        self.planner = SimpleNamespace(settings=RollingHorizonSettings(window_s=1000))

    def evaluate(self, observation):
        if observation.train_id == "A" and observation.platform_id == "P1":
            self.observation = observation
            if self.hold:
                return (HoldAction("A", self.hold, "forecast validation"),)
        return ()


def events_for(output, trains, policy, gap=90, builder=None):
    component = TrainComponent(
        trains, minimum_gap_s=gap, decision=DecisionPipeline(policy, builder)
    )
    result = run_scenario(
        SimpleNamespace(master_seed=7, duration_s=1000),
        lambda seed: None,
        lambda scenario, streams: [component],
        output,
    )
    return [
        json.loads(line) for line in result.events_path.read_text().splitlines()
    ], result
