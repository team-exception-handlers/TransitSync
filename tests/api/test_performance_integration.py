# AI contribution: 50% or more AI-generated
"""Streaming preparation preserves the response contracts added on current main.

Small fixed-seed fixtures cover actual Coordinated decisions, chart data and
comparison cache behavior. Their smaller hold grid is for functional tests;
the opt-in production benchmarks still use the unchanged 300-second limit.
"""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import api.simulation_run as simulation_run
from api.main import create_app
from simulator.control.rolling_horizon import RollingHorizonPlanner


@pytest.fixture
def short_run(monkeypatch):
    """Retain real network/events while bounding only this test's duration."""
    original = simulation_run.SimulationRunService._load_scenario

    def load(service, *args, **kwargs):
        return replace(original(service, *args, **kwargs), duration_s=60)

    monkeypatch.setattr(simulation_run.SimulationRunService, "_load_scenario", load)


@pytest.mark.parametrize("strategy", ["rolling_horizon", "adaptive"])
def test_streaming_and_full_audit_readers_return_identical_responses(
    short_run, monkeypatch, strategy
):
    """Compare every response byte, including new chart, outcome and rule fields."""
    request = dict(
        connection_id="mcgill-rem-green", strategy=strategy, max_hold_time=10
    )
    if strategy == "adaptive":
        request["irregularity_threshold"] = 0.2
    with TestClient(create_app()) as client:
        streamed = client.post("/simulation/run", json=request)
    streamed.raise_for_status()
    monkeypatch.setattr(
        simulation_run,
        "_decision_playback",
        lambda source, path, events, connection: simulation_run._read_json_lines(path),
    )
    with TestClient(create_app()) as client:
        full = client.post("/simulation/run", json=request)
    full.raise_for_status()
    assert streamed.content == full.content


def test_coordinated_comparison_matches_the_cached_station_response(
    short_run, monkeypatch
):
    """Exercise real planning through the comparison endpoint and verify reuse."""
    plans = []
    original = RollingHorizonPlanner.plan

    def plan(planner, observation):
        result = original(planner, observation)
        plans.append(result)
        return result

    monkeypatch.setattr(RollingHorizonPlanner, "plan", plan)
    request = dict(
        connection_id="mcgill-rem-green", strategy="rolling_horizon", max_hold_time=10
    )
    with TestClient(create_app()) as client:
        compared = client.post("/simulation/passenger-comparison", json=request)
        compared.raise_for_status()
        count = len(plans)
        selected = client.post("/simulation/run", json=request)
        selected.raise_for_status()
        baseline = client.post(
            "/simulation/run",
            json={
                "connection_id": request["connection_id"],
                "strategy": "no_control",
            },
        )
        baseline.raise_for_status()
    assert count > 0
    assert len(plans) == count
    assert compared.json()["selected_strategy"] == selected.json()["passenger_outcomes"]
    assert compared.json()["without_holding"] == baseline.json()["passenger_outcomes"]
