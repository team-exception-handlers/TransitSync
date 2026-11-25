# AI contribution: 50% or more AI-generated
"""Paired holding and no-holding runs for the side-by-side view (US-4.1, #230).

Runs use the committed Édouard-Montpetit scenario, so no external service is needed.
"""

import pytest
from fastapi.testclient import TestClient

import api.simulation_comparison as simulation_comparison
from api.main import create_app
from api.passenger_outcomes import PassengerOutcome, match_passengers
from api.passenger_split import split_passengers
from api.simulation_comparison import (
    CONTROL_ONLY_FIELDS,
    DEFAULT_HOLDING_STRATEGY,
    paired_requests,
)
from api.simulation_run import SimulationRunRequest, SimulationRunService

# High demand at Édouard-Montpetit: since the keyed draws (#192) the seeded
# McGill runs have no transfer worth a hold at any demand, so the holding side
# would show no holds.
SETTINGS = {
    "connection_id": "edouard_montpetit-rem-blue",
    "strategy": "connection_protection",
    "passenger_flow": "High",
}
# Fields a single-run playback needs to match across both sides of the pair.
SHARED_FIELDS = ("duration_s", "start_clock_s", "platforms", "connections")


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Share one app, and so one run cache, across this module's API tests."""
    return TestClient(create_app())


@pytest.fixture(scope="module")
def comparison(client: TestClient) -> dict:
    """Return the Édouard-Montpetit connection-protection comparison payload."""
    response = client.post("/simulation/comparison", json=SETTINGS)
    assert response.status_code == 200
    return response.json()


def test_paired_requests_differ_only_in_strategy_and_control_fields():
    request = SimulationRunRequest(
        connection_id="mcgill-rem-green",
        strategy="connection_protection",
        max_hold_time=60.0,
        error_magnitude=2.0,
        passenger_flow="High",
        disruption_preset="platform_delay",
        disruption_time_s=300.0,
    )
    holding, no_holding = paired_requests(request)
    assert holding == request
    assert no_holding.strategy == "no_control"
    unchanged = set(SimulationRunRequest.model_fields) - CONTROL_ONLY_FIELDS
    for field in unchanged - {"strategy"}:
        assert getattr(no_holding, field) == getattr(request, field), field
    # Control-only sliders fall back to defaults so the baseline is cached once.
    assert no_holding.max_hold_time == 300.0
    assert no_holding.error_magnitude == 1.0


def test_no_control_selection_falls_back_to_connection_protection():
    request = SimulationRunRequest(
        connection_id="mcgill-rem-green", strategy="no_control", max_hold_time=90.0
    )
    holding, no_holding = paired_requests(request)
    assert holding.strategy == DEFAULT_HOLDING_STRATEGY
    assert holding.max_hold_time == 90.0
    assert no_holding.strategy == "no_control"


def test_comparison_shares_starting_conditions(comparison: dict):
    assert comparison["holding_strategy"] == "connection_protection"
    assert comparison["service_date"] == "2026-10-05"
    assert comparison["master_seed"] == 42
    assert comparison["duration_s"] == 3600
    holding, no_holding = comparison["holding"], comparison["no_holding"]
    for field in SHARED_FIELDS:
        assert holding[field] == no_holding[field], field
    assert holding["duration_s"] == comparison["duration_s"]


def test_only_the_holding_side_holds_trains(comparison: dict):
    assert comparison["holding"]["time_series"]["hold_events"]
    assert comparison["no_holding"]["time_series"]["hold_events"] == []


def test_each_side_equals_a_direct_run(client: TestClient, comparison: dict):
    for key, strategy in [
        ("holding", SETTINGS["strategy"]),
        ("no_holding", "no_control"),
    ]:
        run = client.post("/simulation/run", json={**SETTINGS, "strategy": strategy})
        assert run.status_code == 200
        assert comparison[key] == run.json()


def test_same_request_twice_gives_the_same_payload(comparison: dict):
    # A fresh app has an empty cache, so this reruns both simulations.
    again = TestClient(create_app()).post("/simulation/comparison", json=SETTINGS)
    assert again.json() == comparison


def test_split_covers_every_passenger_of_the_pair(comparison: dict):
    # Rebuilt from the two sides in the payload, so the split is of this pair
    held, baseline = (
        [PassengerOutcome(**o) for o in comparison[side]["passenger_outcomes"]]
        for side in ("holding", "no_holding")
    )
    matched = match_passengers(held, baseline)
    split = comparison["passenger_split"]
    assert split == split_passengers(matched, comparison["duration_s"]).model_dump()
    groups = ("better_off", "worse_off", "unaffected", "not_compared")
    assert sum(split[group] for group in groups) == len(matched)
    # The holding side holds trains here, so someone catches a held train
    assert split["better_off"] > 0
    assert split["average_time_saved_s"] == pytest.approx(
        split["total_time_saved_s"] / split["better_off"]
    )


def test_runs_that_are_not_a_pair_return_a_server_error(monkeypatch):
    # Edge: one ID on two connections must not become a wrong split
    def not_a_pair(*_runs):
        raise ValueError("passenger p is on two connections")

    monkeypatch.setattr(simulation_comparison, "match_passengers", not_a_pair)
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post("/simulation/comparison", json=SETTINGS)
    assert response.status_code == 500
    assert response.json()["detail"] == "Simulation comparison failed"


def test_unknown_connection_returns_not_found(client: TestClient):
    response = client.post(
        "/simulation/comparison", json={**SETTINGS, "connection_id": "nowhere"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown connection: nowhere"


@pytest.mark.parametrize(
    "override",
    [{"max_hold_time": 301}, {"strategy": "teleport"}, {"error_magnitude": -1}],
)
def test_invalid_settings_return_unprocessable(client: TestClient, override: dict):
    response = client.post("/simulation/comparison", json={**SETTINGS, **override})
    assert response.status_code == 422


def test_baseline_runs_once_across_slider_changes(monkeypatch):
    runs = []
    run_uncached = SimulationRunService._run_uncached

    def record_run(service, request):
        runs.append((request.strategy, request.max_hold_time))
        return run_uncached(service, request)

    monkeypatch.setattr(SimulationRunService, "_run_uncached", record_run)
    client = TestClient(create_app())
    for hold in (300, 60):
        response = client.post(
            "/simulation/comparison", json={**SETTINGS, "max_hold_time": hold}
        )
        assert response.status_code == 200
    assert sorted(runs) == [
        ("connection_protection", 60),
        ("connection_protection", 300),
        ("no_control", 300),
    ]
