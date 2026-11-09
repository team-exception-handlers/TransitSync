# AI contribution: 50% or more AI-generated
"""What the strategy saw next to the true values (US-2.1 demo steps 1 to 3, #39).

The hand-made snapshot matches ``test_prediction_error``: at 100 s train A is
due at P2 at 220 s (horizon 120 s, sigma 73.4265 s) with 300 on board, B has
no next stop, and group g1 has 12 of its 15 passengers still walking.
"""

import json
from types import SimpleNamespace

import pytest

from simulator.control.decision import DecisionPipeline
from simulator.control.decision_audit import KIND_ESTIMATES, estimates_record
from simulator.control.interface import (
    IncomingTransfer,
    ObservationSnapshot,
    PlatformState,
    TrainState,
)
from simulator.control.prediction_error import (
    PredictionErrorModel,
    PredictionErrorSettings,
)
from simulator.engine.random_streams import StreamManager
from simulator.engine.runner import run_scenario
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


class FixedDraws:
    """Generator stand-in returning the given standard normal values in order."""

    def __init__(self, *values):
        self.values = list(values)

    def standard_normal(self):
        return self.values.pop(0)


def snapshot():
    trains = (
        TrainState("A", "rem", "P2", 220.0, 230.0, 15.0, 300, 780),
        TrainState("B", "rem", None, None, None, 0.0, 40, 780),
    )
    return ObservationSnapshot(
        time_s=100.0,
        train_id="A",
        station_id="S1",
        platform_id="P1",
        scheduled_departure_s=130.0,
        trains=trains,
        platforms=(PlatformState("P2", 25, 60.0),),
        incoming_transfers=(IncomingTransfer("g1", "P2", 12, 140.0, 190.0, 90.0, 15),),
    )


def make_trains():
    # A visits P1 (100-130) then P2 (200-230); B visits P1 (400-430)
    return [
        Train(
            "A",
            800,
            (ScheduledStop("S1", "P1", 100, 130), ScheduledStop("S2", "P2", 200, 230)),
        ),
        Train("B", 800, (ScheduledStop("S1", "P1", 400, 430),)),
    ]


def run_with_kappa(tmp_path, kappa):
    """Run with every kappa set to ``kappa``; return the pipeline and records."""
    settings = PredictionErrorSettings(kappa, kappa, kappa)
    stream = StreamManager(7).get_stream("prediction_errors")
    decision = DecisionPipeline(error_model=PredictionErrorModel(settings, stream))
    result = run_scenario(
        SimpleNamespace(master_seed=7, duration_s=1000.0),
        lambda _seed: None,
        lambda _scenario, _streams: [TrainComponent(make_trains(), decision=decision)],
        tmp_path,
    )
    lines = result.decisions_path.read_text(encoding="utf-8").splitlines()
    return decision, [json.loads(line) for line in lines]


def arrival_gaps(records):
    """Seen minus true arrival, in seconds, for every train with a next stop."""
    return [
        train["predicted_arrival_s"]["seen"] - train["predicted_arrival_s"]["true"]
        for record in records
        for train in record["trains"]
        if train["predicted_arrival_s"]["true"] is not None
    ]


def test_record_puts_each_estimate_next_to_its_true_value():
    # Draw order: A load, A arrival, B load, transfer group
    truth = snapshot()
    draws = FixedDraws(1.0, -0.5, 0.0, 2.0)
    seen = PredictionErrorModel(PredictionErrorSettings(), draws).apply(truth)
    record = estimates_record(truth, seen)
    assert record["kind"] == KIND_ESTIMATES
    assert (record["time_s"], record["train_id"], record["platform_id"]) == (
        100.0,
        "A",
        "P1",
    )
    a, b = record["trains"]
    # 220 - 0.5 * 73.4265 = 183.2867; load 300 * 1.1 = 330
    assert a["predicted_arrival_s"]["true"] == 220.0
    assert a["predicted_arrival_s"]["seen"] == pytest.approx(183.2867, abs=1e-4)
    assert a["onboard_load"] == {"seen": 330, "true": 300}
    # B has no next stop, so there is no arrival to estimate
    assert b["predicted_arrival_s"] == {"seen": None, "true": None}
    # 12 * 1.2 = 14.4 -> 14 still walking; 15 * 1.2 = 18 in the group
    assert record["transfers"] == [
        {
            "group_id": "g1",
            "passenger_count": {"seen": 14, "true": 12},
            "group_size": {"seen": 18, "true": 15},
        }
    ]


def test_run_writes_one_estimates_record_per_decision(tmp_path):
    # Demo step 1: A decides at P1 and P2, B at P1, and none of them holds
    _, records = run_with_kappa(tmp_path, 1.0)
    assert [(r["kind"], r["train_id"], r["platform_id"]) for r in records] == [
        (KIND_ESTIMATES, "A", "P1"),
        (KIND_ESTIMATES, "A", "P2"),
        (KIND_ESTIMATES, "B", "P1"),
    ]


def test_gap_doubles_when_kappa_doubles(tmp_path):
    # Demo steps 2 and 3: same draws, so every arrival gap scales with kappa
    _, one = run_with_kappa(tmp_path / "one", 1.0)
    _, two = run_with_kappa(tmp_path / "two", 2.0)
    gaps = arrival_gaps(one)
    assert gaps
    assert all(gap != 0 for gap in gaps)
    assert arrival_gaps(two) == pytest.approx([2 * gap for gap in gaps])


def test_perfect_information_shows_seen_equal_to_true(tmp_path):
    _, records = run_with_kappa(tmp_path, 0.0)
    values = [
        value
        for record in records
        for train in record["trains"]
        for value in (train["predicted_arrival_s"], train["onboard_load"])
    ]
    assert values
    assert all(value["seen"] == value["true"] for value in values)


def test_changing_returned_records_leaves_the_log_unchanged(tmp_path):
    decision, _ = run_with_kappa(tmp_path, 1.0)
    decision.decision_records()[0]["trains"].clear()
    assert decision.decision_records()[0]["trains"]
