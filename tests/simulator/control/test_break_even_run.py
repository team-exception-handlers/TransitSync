# AI contribution: 50% or more AI-generated
"""Break-even holds inside full runs (US-2.2 blackbox test, #32).

The real connection protection strategy is #51, so a test-only strategy
calls the search and the audit log the same way it will. Setup at McGill:

- REM feeder ``rem-1`` arrives at 100 s; its transfer group walks to green
  with F(t) = 1 - exp(-(t - 30) / 90), so nobody walks in under 30 s
- green ``green-1`` carries L = 400 and is ready to leave at 130 s, so
  s = 30 s and F(s) = 0
- H = 300 s and the default weights 2 and 1, so J(h) = 600 * N(h) - 400 * h

The first second of holding catches about M / 90 passengers, worth
600 * M / 90 passenger-seconds against a cost of 400, so it only pays when
M > 60. Demand of 120 per minute over the 100 s before the feeder gives
M of about 200 (hold); 12 per minute gives about 20 (no hold).
"""

import json
import math
from types import SimpleNamespace

from simulator.control.break_even import BreakEvenWeights
from simulator.control.decision import DecisionPipeline
from simulator.control.decision_audit import DecisionAuditLog
from simulator.control.hold_search import HoldInputs, HoldSearch
from simulator.control.interface import DecisionController, HoldAction
from simulator.control.observation_builder import ObservationBuilder
from simulator.control.walking_cdf import ShiftedExponentialCdf
from simulator.engine.random_streams import StreamManager
from simulator.engine.runner import run_scenario
from simulator.passengers import (
    CorridorQueue,
    DemandPeriod,
    DemandProfile,
    TransferComponent,
    TransferRoute,
)
from simulator.passengers.platform_queue import PlatformQueue
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent

WALK_MEAN_S = 120.0
WALK_MIN_S = 30.0
HEADWAY_S = 300.0


class BreakEvenProbe(DecisionController):
    """Test stand-in for #51: search, record, then hold if worthwhile."""

    name = "break_even_probe"

    def __init__(self):
        self.search = HoldSearch(ShiftedExponentialCdf(WALK_MEAN_S, WALK_MIN_S))
        self.log = DecisionAuditLog()

    def evaluate(self, observation):
        result = self.search.run(HoldInputs.from_observation(observation, HEADWAY_S))
        self.log.record(result)
        if result.chosen is None:
            return ()
        return (HoldAction(observation.train_id, result.hold_s, result.reason),)

    def decision_records(self):
        return self.log.decision_records()


def run(tmp_path, rate_per_min):
    streams = StreamManager(42)
    route = TransferRoute(
        station_id="mcgill",
        feeder_platform_id="rem",
        connecting_platform_id="green",
        demand_profile=DemandProfile((DemandPeriod(0, 1000, rate_per_min),)),
        transfer_fractions={"bonaventure": 1},
        corridor=CorridorQueue(6000),
        walking_mean_s=WALK_MEAN_S,
        walking_min_s=WALK_MIN_S,
    )
    transfers = TransferComponent([route], streams)
    pipeline = DecisionPipeline(
        BreakEvenProbe(), builder=ObservationBuilder([transfers])
    )
    trains = TrainComponent(
        [
            Train("rem-1", 800, (ScheduledStop("mcgill", "rem", 100, 130),)),
            Train(
                "green-1",
                800,
                (ScheduledStop("mcgill", "green", 100, 130),),
                onboard_load=400,
            ),
        ],
        passenger_queue=PlatformQueue(("green",)),
        decision=pipeline,
    )
    result = run_scenario(
        SimpleNamespace(master_seed=42, duration_s=600),
        lambda seed: streams,
        lambda scenario, built: [transfers, trains],
        tmp_path,
    )
    events = [json.loads(line) for line in result.events_path.read_text().splitlines()]
    decisions = [
        json.loads(line) for line in result.decisions_path.read_text().splitlines()
    ]
    return events, decisions


def green_decision(decisions):
    [record] = [r for r in decisions if r["train_id"] == "green-1"]
    return record


def holds(events):
    return [e for e in events if e["event_type"] == "hold"]


def test_high_transfer_volume_issues_a_hold(tmp_path):
    events, decisions = run(tmp_path, rate_per_min=120)
    record = green_decision(decisions)
    assert record["chosen_hold_s"] > 0
    [hold] = holds(events)
    assert hold["train_id"] == "green-1"
    assert hold["requested_s"] == record["chosen_hold_s"]
    assert hold["reason"] == record["reason"]


def test_low_transfer_volume_declines_at_the_same_decision_point(tmp_path):
    events, decisions = run(tmp_path, rate_per_min=12)
    record = green_decision(decisions)
    assert record["chosen_hold_s"] == 0.0
    assert record["reason"].startswith("no hold: best was")
    assert holds(events) == []


def test_every_decision_point_is_recorded_including_declines(tmp_path):
    _, decisions = run(tmp_path, rate_per_min=120)
    # rem-1 also decides at 130 s; nobody walks to its platform
    assert sorted(r["train_id"] for r in decisions) == ["green-1", "rem-1"]


def test_logged_decision_recalculates_by_hand(tmp_path):
    _, decisions = run(tmp_path, rate_per_min=120)
    record = green_decision(decisions)
    [group] = record["inputs"]["transfers"]
    size, window = group["group_size"], group["conn_window_s"]
    load = record["inputs"]["load"]
    weights = BreakEvenWeights(**record["weights"])
    assert (window, load) == (30.0, 400)
    for candidate in record["candidates"]:
        hold = candidate["hold_s"]
        # F(30) = 0, so N(h) = M * F(30 + h) = M * (1 - exp(-h / 90))
        caught = size * (1.0 - math.exp(-hold / (WALK_MEAN_S - WALK_MIN_S)))
        net = caught * HEADWAY_S * weights.w_wait - load * hold * weights.w_onboard
        assert math.isclose(candidate["net_ps"], net, abs_tol=1e-6)


def test_decision_log_is_byte_reproducible(tmp_path):
    run(tmp_path / "first", rate_per_min=120)
    run(tmp_path / "second", rate_per_min=120)
    first = (tmp_path / "first" / "decisions.jsonl").read_bytes()
    second = (tmp_path / "second" / "decisions.jsonl").read_bytes()
    assert first == second
