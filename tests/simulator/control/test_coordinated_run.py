# AI contribution: 50% or more AI-generated
"""US-2.6 #61/#62: decline a locally profitable hold in a full coordinated run."""

import json

import pytest

from simulator.control.hold_search import HoldSearchSettings
from simulator.control.observation_builder import ObservationBuilder
from simulator.control.planning import RollingHorizonSettings
from simulator.control.rolling_horizon import RollingHorizonPlanner
from simulator.control.strategies.rolling_horizon import RollingHorizonStrategy
from simulator.trains.train import ScheduledStop, Train
from tests.simulator.control.downstream_helpers import harmful_snapshot
from tests.simulator.control.downstream_run_helpers import events_for
from tests.simulator.control.rolling_helpers import UniformWalk, group


class WalkingGroup:
    def incoming_transfers(self):
        return (group(),)


def run_harmful(output, window):
    seen = harmful_snapshot()
    trains = [
        Train(
            t.train_id,
            800,
            tuple(
                ScheduledStop(
                    v.station_id,
                    v.platform_id,
                    v.scheduled_arrival_s,
                    v.scheduled_departure_s,
                )
                for v in seen.future_visits
                if v.train_id == t.train_id
            ),
            onboard_load=t.onboard_load,
        )
        for t in seen.trains
    ]
    policy = RollingHorizonStrategy(
        RollingHorizonPlanner(
            {"P1": UniformWalk()},
            RollingHorizonSettings(window),
            HoldSearchSettings(10, 10),
        )
    )
    return events_for(
        output, trains, policy, gap=10, builder=ObservationBuilder([WalkingGroup()])
    )


def test_full_run_rejects_local_gain_when_downstream_loss_enters_window(tmp_path):
    local, _ = run_harmful(tmp_path / "local", 300)
    global_events, result = run_harmful(tmp_path / "global", 600)
    assert [
        (e["train_id"], e["applied_s"]) for e in local if e["event_type"] == "hold"
    ] == [("A", 10)]
    assert [e for e in global_events if e["event_type"] == "hold"] == []
    local_b = next(
        e["time_s"]
        for e in local
        if e["event_type"] == "train_departure"
        and e["train_id"] == "B"
        and e["platform_id"] == "P2"
    )
    global_b = next(
        e["time_s"]
        for e in global_events
        if e["event_type"] == "train_departure"
        and e["train_id"] == "B"
        and e["platform_id"] == "P2"
    )
    assert local_b - global_b == pytest.approx(10, abs=1e-9)
    records = [
        json.loads(line) for line in result.decisions_path.read_text().splitlines()
    ]
    assert records[0]["chosen_hold_s"] == 0
    rejected = next(a for a in records[0]["alternatives"] if a["hold_s"] == 10)
    assert rejected["local_net_ps"] == 300
    assert rejected["downstream_cost_ps"] == pytest.approx(5000, abs=1e-6)
    assert rejected["net_ps"] == pytest.approx(-4700, abs=1e-6)
    assert (
        records[0]["net_ps"]
        == records[0]["local_net_ps"] - records[0]["downstream_cost_ps"]
    )
