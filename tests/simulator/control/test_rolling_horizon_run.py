# AI contribution: 50% or more AI-generated
"""#61 integration with real pulsed transfers, rules, movements and audit files."""

import json
from types import SimpleNamespace

from simulator.control.decision import DecisionPipeline
from simulator.control.hold_search import HoldSearchSettings
from simulator.control.observation_builder import ObservationBuilder
from simulator.control.planning import RollingHorizonSettings
from simulator.control.rolling_horizon import RollingHorizonPlanner
from simulator.control.rules import OperatingRulesEnforcer
from simulator.control.settings import OperatingRulesConfig
from simulator.control.strategies.rolling_horizon import RollingHorizonStrategy
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


def make_transfers(streams):
    """Build the run's pulsed route with matching walking-time parameters."""
    route = TransferRoute(
        "S1",
        "feeder",
        "P1",
        DemandProfile((DemandPeriod(0, 2000, 120),)),
        {"S2": 1},
        CorridorQueue(6000),
        walking_mean_s=120,
        walking_min_s=30,
    )
    return TransferComponent([route], streams)


def run(output, cap=300):
    """Run fresh transfers and trains with the selected operating-rule cap."""
    streams = StreamManager(42)
    transfers = make_transfers(streams)
    policy = RollingHorizonStrategy(
        RollingHorizonPlanner(
            {"P1": ShiftedExponentialCdf(120, 30)},
            RollingHorizonSettings(300),
            HoldSearchSettings(10, 10),
        )
    )
    pipeline = DecisionPipeline(
        policy,
        ObservationBuilder([transfers]),
        OperatingRulesEnforcer(OperatingRulesConfig(max_hold_time=cap)),
    )
    trains = TrainComponent(
        [
            Train("feeder", 800, (ScheduledStop("S1", "feeder", 80, 90),)),
            Train(
                "A",
                800,
                (
                    ScheduledStop("S1", "P1", 100, 110),
                    ScheduledStop("S2", "P2", 200, 210),
                ),
                onboard_load=10,
            ),
            Train("next", 800, (ScheduledStop("S1", "P1", 1100, 1110),)),
        ],
        passenger_queue=PlatformQueue(("P1",)),
        decision=pipeline,
    )
    result = run_scenario(
        SimpleNamespace(master_seed=42, duration_s=1300),
        lambda seed: streams,
        lambda scenario, built: [transfers, trains],
        output,
    )
    events = [json.loads(line) for line in result.events_path.read_text().splitlines()]
    records = [
        json.loads(line) for line in result.decisions_path.read_text().splitlines()
    ]
    return result, events, records


def test_real_transfers_hold_only_current_visit_and_propagate_delay(tmp_path):
    _, events, records = run(tmp_path)
    holds = [e for e in events if e["event_type"] == "hold"]
    assert [(e["train_id"], e["time_s"], e["applied_s"]) for e in holds] == [
        ("A", 110, 10)
    ]
    departures = [
        e
        for e in events
        if e["event_type"] == "train_departure" and e["train_id"] == "A"
    ]
    assert [e["time_s"] for e in departures] == [120, 220]
    first = next(r for r in records if r["train_id"] == "A")
    assert [d["visit"]["station_id"] for d in first["plan"]] == ["S1", "S2"]
    assert [r["time_s"] for r in records if r["train_id"] == "A"] == [110, 220]


def test_operating_rule_clamp_is_applied_by_pipeline(tmp_path):
    _, events, _ = run(tmp_path, cap=5)
    [hold] = [e for e in events if e["event_type"] == "hold"]
    assert hold["requested_s"] == 10
    assert hold["applied_s"] == 5
    departure = next(
        e
        for e in events
        if e["event_type"] == "train_departure" and e["train_id"] == "A"
    )
    assert departure["time_s"] == 115


def test_seeded_event_and_decision_files_are_byte_reproducible(tmp_path):
    first, _, _ = run(tmp_path / "first")
    second, _, _ = run(tmp_path / "second")
    assert first.events_path.read_bytes() == second.events_path.read_bytes()
    assert first.decisions_path.read_bytes() == second.decisions_path.read_bytes()
