# AI contribution: 50% or more AI-generated
"""US-2.6 #62: compare pure forecasts with actual engine departures."""

import pytest

from simulator.control.downstream import project_visits
from simulator.trains.train import ScheduledStop, Train
from tests.simulator.control.downstream_helpers import cascade
from tests.simulator.control.downstream_run_helpers import CaptureHold, events_for


@pytest.mark.parametrize("hold", [0, 10, 100])
def test_projection_matches_train_engine_over_three_stations(tmp_path, hold):
    fixture = cascade()
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
                for v in fixture.future_visits
                if v.train_id == t.train_id
            ),
            onboard_load=t.onboard_load,
        )
        for t in fixture.trains
    ]
    policy = CaptureHold(hold)
    events, _ = events_for(tmp_path, trains, policy)
    projected = project_visits(policy.observation, {("A", 0, 0): hold}, 1000)
    actual = {
        (e["train_id"], e["platform_id"]): e["time_s"]
        for e in events
        if e["event_type"] == "train_departure"
    }
    assert {
        (p.visit.train_id, p.visit.platform_id): p.departure_s for p in projected
    } == actual


def test_projection_matches_engine_through_terminal_recovery(tmp_path):
    train = Train(
        "A",
        800,
        (ScheduledStop("S1", "P1", 90, 100), ScheduledStop("S2", "T", 200, 210)),
        layover_slack=5,
        return_trips=(
            (ScheduledStop("S2", "R", 300, 310), ScheduledStop("S3", "P3", 400, 410)),
        ),
    )
    policy = CaptureHold(10)
    events, _ = events_for(tmp_path, [train], policy)
    forecast = project_visits(policy.observation, {("A", 0, 0): 10}, 1000)
    actual = {
        (e["train_id"], e["platform_id"]): e["time_s"]
        for e in events
        if e["event_type"] == "train_departure"
    }
    assert {
        (p.visit.train_id, p.visit.platform_id): p.departure_s
        for p in forecast
        if not p.visit.skips_departure
    } == actual
    assert actual[("A", "R")] == 315
