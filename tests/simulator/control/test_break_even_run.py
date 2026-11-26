# AI contribution: 50% or more AI-generated
"""Break-even holds inside full runs (US-2.2 blackbox test, #32, #51).

Run the production strategy through the simulator and its hold rules at McGill:

- REM feeder ``rem-1`` arrives at 100 s; its transfer group walks to green
  with F(t) = 1 - exp(-(t - 30) / 90), so nobody walks in under 30 s
- green ``green-1`` carries L = 400 and is ready to leave at 130 s, so
  s = 30 s and F(s) = 0
- H = 300 s and the default weights 2 and 1, so J(h) = 600 * N(h) - 400 * h

The first second of holding catches about M / 90 passengers, worth
600 * M / 90 passenger-seconds against a cost of 400, so it only pays when
M > 60. Demand of 120 per minute over the 100 s before the feeder gives
M of about 200 (hold); 12 per minute gives about 20 (no hold).

Only green receives transfers in this setup. REM departures should have no
hold search or decision record. Record green's holds and declined holds alike.

The search tries holds up to 60s. The normal operating limit is 300s,
so it accepts the winning proposal unchanged. The cap test lowers that
limit to 20s. CLAMP reduces the requested 60 s hold to the allowed 20s.
REFUSE rejects the request and applies no hold (0s).
The decision file keeps the proposal; the event file records the applied hold.

Load connection_protection from saved scenario JSON for every run.
The factory reads its headways, weights and search limits.
Walking values come from the same routes used to generate passengers.
The manifest must keep the selected settings so results can be reproduced.
"""

import json
import math
from datetime import date
from functools import partial

import pytest

from simulator.control.break_even import BreakEvenWeights
from simulator.control.connection_configuration import (
    build_selected_connection_protection,
)
from simulator.control.decision import DecisionPipeline
from simulator.control.decision_audit import KIND_HOLD_SEARCH
from simulator.control.observation_builder import ObservationBuilder
from simulator.control.prediction_error import PredictionErrorModel
from simulator.control.rules import OperatingRulesEnforcer
from simulator.control.settings import OperatingRulesConfig
from simulator.control.strategies import STRATEGIES
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
from simulator.scenario import DatasetMetadata, load_scenario_json
from simulator.trains.suspension import LineSuspension
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent

WALK_MEAN_S = 120.0
WALK_MIN_S = 30.0
HEADWAY_S = 300.0


def build_components(scenario, streams, rate_per_min, clearance_s=None):
    """Build trains and passengers using shared routes and saved control settings.
    Demand is passengers/minute; clearance_s is when dispatch can resume."""
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
    routes = [route]
    transfers = TransferComponent(routes, streams)
    strategy = (
        build_selected_connection_protection(scenario.control, routes, ("rem", "green"))
        if scenario.control.strategy == "connection_protection"
        else STRATEGIES.build(scenario.control.strategy)
    )
    pipeline = DecisionPipeline(
        strategy,
        builder=ObservationBuilder([transfers]),
        enforcer=OperatingRulesEnforcer(scenario.operating_rules),
        error_model=PredictionErrorModel(
            scenario.control.prediction_error,
            partial(streams.keyed_normal, "prediction_errors"),
        ),
    )
    trains = TrainComponent(
        [
            Train(
                "rem-1", 800, (ScheduledStop("mcgill", "rem", 100, 130),), line_id="rem"
            ),
            Train(
                "green-1",
                800,
                (ScheduledStop("mcgill", "green", 100, 130),),
                onboard_load=400,
                line_id="green",
            ),
        ],
        passenger_queue=PlatformQueue(("green",)),
        decision=pipeline,
        control=scenario.control,
        suspensions=()
        if clearance_s is None
        else (LineSuspension("green", 130, clearance_s),),
    )
    return [transfers, trains]


def run(
    tmp_path,
    rate_per_min,
    rules=None,
    *,
    clearance_s=None,
    strategy="connection_protection",
):
    """Load saved settings and run seed 42 with prediction error turned off."""
    dataset = DatasetMetadata(
        "test",
        date(2026, 10, 5),
        date(2026, 10, 5),
        {"mcgill": 86400},
        frozenset({"mcgill"}),
    )
    values = {
        "dataset_id": "test",
        "date": "2026-10-05",
        "start_time": "07:00",
        "duration_s": 600,
        "master_seed": 42,
        "interchanges": ["mcgill"],
        "control": {
            "strategy": strategy,
            "connection_headways_s": {"green": HEADWAY_S},
            "prediction_error": {
                "arrival_kappa": 0,
                "transfer_kappa": 0,
                "load_kappa": 0,
            },
        },
        "operating_rules": (rules or OperatingRulesConfig()).to_dict(),
    }
    if strategy == "no_control":
        del values["control"]["connection_headways_s"]
    scenario = load_scenario_json(json.dumps(values), {"test": dataset})
    result = run_scenario(
        scenario,
        StreamManager,
        lambda settings, built: build_components(
            settings, built, rate_per_min, clearance_s
        ),
        tmp_path,
    )
    events = [json.loads(line) for line in result.events_path.read_text().splitlines()]
    records = map(json.loads, result.decisions_path.read_text().splitlines())
    # The error model also writes an estimates record per decision (#39)
    decisions = [r for r in records if r["kind"] == KIND_HOLD_SEARCH]
    return events, decisions


def green_decision(decisions):
    """Read green's one decision record; fail if it is missing or duplicated."""
    [record] = [r for r in decisions if r["train_id"] == "green-1"]
    return record


def holds(events):
    """Read hold events, including requests that the rules refused."""
    return [e for e in events if e["event_type"] == "hold"]


def test_high_transfer_volume_issues_a_hold(tmp_path):
    """The strategy asks for 60s, so green leaves at 130 + 60 = 190s."""
    events, decisions = run(tmp_path, rate_per_min=120)
    record = green_decision(decisions)
    assert record["chosen_hold_s"] == 60.0
    [hold] = holds(events)
    assert hold["train_id"] == "green-1"
    assert hold["requested_s"] == record["chosen_hold_s"]
    assert hold["reason"] == record["reason"]
    assert (hold["time_s"], hold["requested_s"], hold["applied_s"]) == (130, 60, 60)
    ends = [e for e in events if e["event_type"] == "hold_end"]
    assert [(e["train_id"], e["time_s"]) for e in ends] == [("green-1", 190)]
    departures = [e for e in events if e["event_type"] == "train_departure"]
    assert [(e["train_id"], e["time_s"], e["hold_s"]) for e in departures] == [
        ("rem-1", 130, 0),
        ("green-1", 190, 60),
    ]
    # There are no disruptions here: green's 60s of lateness comes from holding.
    green = departures[1]
    assert green["time_s"] - green["scheduled_s"] == 60
    assert green["generated_delay_s"] == 60
    assert green["inherited_delay_s"] == 0
    assert green["disruption_delay_s"] == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["control"] == {
        "strategy": "connection_protection",
        "connection_headways_s": {"green": 300},
        "hold_search": {"step_s": 5, "max_hold_s": 60},
        "weights": {"w_wait": 2, "w_onboard": 1},
        "prediction_error": {
            "arrival_kappa": 0,
            "transfer_kappa": 0,
            "load_kappa": 0,
        },
    }


def test_low_transfer_volume_declines_at_the_same_decision_point(tmp_path):
    """With little transfer demand, both trains leave at 130s without holds."""
    events, decisions = run(tmp_path, rate_per_min=12)
    record = green_decision(decisions)
    assert record["chosen_hold_s"] == 0.0
    assert record["reason"].startswith("no hold: best was")
    assert holds(events) == []
    departures = [e for e in events if e["event_type"] == "train_departure"]
    assert sorted((e["train_id"], e["time_s"], e["hold_s"]) for e in departures) == [
        ("green-1", 130, 0),
        ("rem-1", 130, 0),
    ]


@pytest.mark.parametrize("rate_per_min", [120, 12])
def test_only_transfer_destination_is_audited_for_holds_and_declines(
    tmp_path, rate_per_min
):
    """Only green receives transfers; REM departures need no search record."""
    _, decisions = run(tmp_path, rate_per_min)
    assert [r["train_id"] for r in decisions] == ["green-1"]


def test_logged_decision_recalculates_by_hand(tmp_path):
    """Recalculate each candidate from its logged group size, wait and load.

    Use a separate formula rather than calling the search for expected values.
    Allow small rounding differences between exp here and expm1 in the model.
    """
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


def test_run_logs_are_byte_reproducible(tmp_path):
    """The same seed must produce identical event and decision files."""
    run(tmp_path / "first", rate_per_min=120)
    run(tmp_path / "second", rate_per_min=120)
    for filename in ("decisions.jsonl", "events.jsonl"):
        first = (tmp_path / "first" / filename).read_bytes()
        second = (tmp_path / "second" / filename).read_bytes()
        assert first == second


@pytest.mark.parametrize(("rule_action", "applied_s"), [("CLAMP", 20), ("REFUSE", 0)])
def test_enforcer_changes_applied_hold_without_changing_proposal(
    tmp_path, rule_action, applied_s
):
    """The strategy asks for 60s, but the operating limit is 20s.

    CLAMP applies 20s instead of 60s. REFUSE applies no hold (0s).
    The decision log keeps the original proposal and reason. Events show what
    was allowed and when green actually leaves: 130 + applied hold seconds.
    """
    rules = OperatingRulesConfig(
        max_hold_time=20, rule_action_map={"max_hold_exceeded": rule_action}
    )
    events, decisions = run(tmp_path, rate_per_min=120, rules=rules)
    [record] = decisions
    assert record["chosen_hold_s"] == 60
    assert record["hold_search"]["max_hold_s"] == 60
    assert record["reason"].startswith("hold 60 s:")
    [hold] = holds(events)
    assert (
        hold["train_id"],
        hold["time_s"],
        hold["requested_s"],
        hold["applied_s"],
    ) == ("green-1", 130, 60, applied_s)
    if rule_action == "CLAMP":
        assert hold["reason"] == record["reason"] + " (clamped to max_hold_time 20 s)"
    else:
        assert hold["reason"] == f"refused: over max hold 20 s ({record['reason']})"
    green = [
        e
        for e in events
        if e["event_type"] == "train_departure" and e["train_id"] == "green-1"
    ]
    assert [(e["time_s"], e["hold_s"]) for e in green] == [(130 + applied_s, applied_s)]
    ends = [e for e in events if e["event_type"] == "hold_end"]
    assert [(e["train_id"], e["time_s"]) for e in ends] == (
        [("green-1", 150)] if applied_s else []
    )


@pytest.mark.parametrize(
    ("clearance_s", "requested_s", "departure"), [(150, 60, 190), (200, 0, 200)]
)
def test_saved_connection_protection_projects_paired_dispatch_departures(
    tmp_path, clearance_s, requested_s, departure
):
    """Check logged departure estimates against actual runs with and without holds."""
    baseline, baseline_decisions = run(
        tmp_path / "baseline", 120, clearance_s=clearance_s, strategy="no_control"
    )
    protected, decisions = run(tmp_path / "protected", 120, clearance_s=clearance_s)
    record = green_decision(decisions)
    assert baseline_decisions == []
    assert record["time_s"] == 130
    assert record["chosen_hold_s"] == requested_s
    assert record["no_hold_departure_s"] == clearance_s
    for events, expected in ((baseline, clearance_s), (protected, departure)):
        [actual] = [
            e
            for e in events
            if e["event_type"] == "train_departure" and e["train_id"] == "green-1"
        ]
        assert actual["time_s"] == expected
        # The 400 spare seats do not limit boarding.
        assert actual["boarded_count"] < 400
    assert holds(baseline) == []
    assert [(e["requested_s"], e["applied_s"]) for e in holds(protected)] == (
        [(requested_s, requested_s)] if requested_s else []
    )
    chosen = next(c for c in record["candidates"] if c["hold_s"] == requested_s)
    assert chosen["departure_s"] == departure
    assert chosen["incremental_delay_s"] == departure - clearance_s
    assert record["departure_context"]["suspensions"] == [
        {"line_id": "green", "start_s": 130, "end_s": clearance_s}
    ]
    [group] = record["inputs"]["transfers"]
    # The train is ready 30 s after the feeder arrives (130 - 100).
    assert group["conn_window_s"] == 30
    mean, minimum = record["walking"]["mean_s"], record["walking"]["min_s"]
    for candidate in record["candidates"]:
        projected = max(clearance_s, 130 + candidate["hold_s"])
        delta = projected - clearance_s
        # F(x)=1-exp(-(x-minimum)/(mean-minimum)). Count only walkers
        # arriving after no-hold departure and by the held departure.
        caught = group["group_size"] * (
            math.exp(-(clearance_s - 100 - minimum) / (mean - minimum))
            - math.exp(-(projected - 100 - minimum) / (mean - minimum))
        )
        assert candidate["departure_s"] == projected
        assert candidate["incremental_delay_s"] == delta
        assert candidate["n_caught"] == pytest.approx(caught, abs=1e-9, rel=0)
        assert candidate["benefit_ps"] == pytest.approx(caught * 600, abs=1e-6, rel=0)
        assert candidate["cost_ps"] == 400 * delta
