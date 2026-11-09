# AI contribution: 50% or more AI-generated
"""#61 integration with real pulsed transfers, rules, movements and audit files."""

import json
from types import SimpleNamespace

import pytest

from simulator.control.decision import DecisionPipeline
from simulator.control.decision_audit import (
    DECISION_SCHEMA_VERSION,
    KIND_ESTIMATES,
    KIND_ROLLING_HORIZON,
)
from simulator.control.hold_search import HoldSearchSettings
from simulator.control.observation_builder import ObservationBuilder
from simulator.control.planning import RollingHorizonSettings
from simulator.control.prediction_error import (
    PredictionErrorModel,
    PredictionErrorSettings,
)
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


def make_transfers(streams, *, walking_mean_s=120, walking_min_s=30):
    """Build transfers and their planner CDF from one route configuration.

    Use the same minimum, mean and connecting platform as the sampler so
    changing a route cannot silently leave the controller's model behind.
    """
    route = TransferRoute(
        "S1",
        "feeder",
        "P1",
        DemandProfile((DemandPeriod(0, 2000, 120),)),
        {"S2": 1},
        CorridorQueue(6000),
        walking_mean_s=walking_mean_s,
        walking_min_s=walking_min_s,
    )
    walking_by_platform = {
        route.connecting_platform_id: ShiftedExponentialCdf(
            mean_s=route.walking_mean_s, min_s=route.walking_min_s
        )
    }
    return TransferComponent([route], streams), walking_by_platform


def run(output, cap=300, *, route_options=None, with_errors=False):
    """Run fresh transfers and trains with the selected operating-rule cap."""
    streams = StreamManager(42)
    error_model = None
    if with_errors:
        stream = streams.get_stream("prediction_errors")
        error_model = PredictionErrorModel(PredictionErrorSettings(), stream)
    transfers, walking_by_platform = make_transfers(streams, **(route_options or {}))
    policy = RollingHorizonStrategy(
        RollingHorizonPlanner(
            walking_by_platform,
            RollingHorizonSettings(300),
            HoldSearchSettings(10, 10),
        )
    )
    pipeline = DecisionPipeline(
        policy,
        ObservationBuilder([transfers]),
        OperatingRulesEnforcer(OperatingRulesConfig(max_hold_time=cap)),
        error_model,
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


def test_every_record_has_a_kind_when_estimates_are_mixed_in(tmp_path):
    # #204 review: a reader filtering on kind must not drop planner records
    _, _, records = run(tmp_path, with_errors=True)
    kinds = [(r["schema_version"], r["kind"], r["train_id"]) for r in records]
    assert kinds == [
        (DECISION_SCHEMA_VERSION, KIND_ROLLING_HORIZON, "feeder"),
        (DECISION_SCHEMA_VERSION, KIND_ROLLING_HORIZON, "A"),
        (DECISION_SCHEMA_VERSION, KIND_ROLLING_HORIZON, "A"),
        (DECISION_SCHEMA_VERSION, KIND_ROLLING_HORIZON, "next"),
        (DECISION_SCHEMA_VERSION, KIND_ESTIMATES, "feeder"),
        (DECISION_SCHEMA_VERSION, KIND_ESTIMATES, "A"),
        (DECISION_SCHEMA_VERSION, KIND_ESTIMATES, "A"),
        (DECISION_SCHEMA_VERSION, KIND_ESTIMATES, "next"),
    ]


def test_seeded_event_and_decision_files_are_byte_reproducible(tmp_path):
    first, _, _ = run(tmp_path / "first")
    second, _, _ = run(tmp_path / "second")
    assert first.events_path.read_bytes() == second.events_path.read_bytes()
    assert first.decisions_path.read_bytes() == second.decisions_path.read_bytes()


@pytest.mark.parametrize(
    "route_options",
    [
        {"walking_mean_s": 300, "walking_min_s": 150},
        {"walking_mean_s": 1_000_000},
    ],
    ids=["minimum-after-hold", "long-mean-low-benefit"],
)
def test_route_walk_parameters_change_the_planners_hold_decision(
    tmp_path, route_options
):
    _, events, records = run(tmp_path, route_options=route_options)
    # Feeder arrival is 80 s. A departs at 110, or 120 with a hold.
    # With min=150 no one can connect by 120. With a million-second mean,
    # even 200 walkers catch <0.002 riders in 10 s: <4 pax-s benefit versus
    # 10 onboard * 10 s = 100 pax-s cost. Neither case warrants holding.
    assert [e for e in events if e["event_type"] == "hold"] == []
    first = next(r for r in records if r["train_id"] == "A")
    assert first["chosen_hold_s"] == 0
    held = next(a for a in first["alternatives"] if a["hold_s"] == 10)
    assert held["local_net_ps"] < 0
