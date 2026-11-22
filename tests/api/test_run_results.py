# AI contribution: 50% or more AI-generated
"""Exercise the results endpoint through the same cache used for playback."""

import pytest
from fastapi.testclient import TestClient

import api.main as main
import api.simulation_run as simulation_run
from api.main import create_app
from api.simulation_run import SimulationRunService
from api.station_layout import load_station_layouts


def create_run(client, strategy):
    response = client.post(
        "/simulation/run",
        json={"connection_id": "mcgill-rem-green", "strategy": strategy},
    )
    assert response.status_code == 200
    return response.json()


def unexpected_run(*args):
    raise AssertionError("A cache lookup reran the simulation")


@pytest.mark.parametrize("strategy", ["no_control", "connection_protection"])
def test_results_match_the_requested_run(monkeypatch, strategy):
    client = TestClient(create_app())
    playback = create_run(client, strategy)
    monkeypatch.setattr(SimulationRunService, "_run_uncached", unexpected_run)

    results = client.get(f"/simulation/runs/{playback['run_id']}/results")
    assert results.status_code == 200
    payload = results.json()
    for key in (
        "run_id",
        "start_clock_s",
        "duration_s",
        "passenger_metrics",
        "time_series",
        "passenger_outcomes",
    ):
        assert payload[key] == playback[key]
    assert "passenger_tracks" not in payload


def test_same_settings_reuse_run_id_without_rerunning(monkeypatch):
    client = TestClient(create_app())
    playback = create_run(client, "no_control")
    monkeypatch.setattr(SimulationRunService, "_run_uncached", unexpected_run)

    response = client.post(
        "/simulation/run", json={"connection_id": "mcgill-rem-green"}
    )
    assert response.status_code == 200
    assert response.json()["run_id"] == playback["run_id"]


def test_evicted_run_results_return_404(monkeypatch):
    monkeypatch.setattr(simulation_run, "MAX_CACHED_RUNS", 1)
    client = TestClient(create_app())
    first = create_run(client, "no_control")
    second = create_run(client, "connection_protection")
    assert first["run_id"] != second["run_id"]
    monkeypatch.setattr(SimulationRunService, "_run_uncached", unexpected_run)

    assert client.get(f"/simulation/runs/{first['run_id']}/results").status_code == 404
    assert client.get(f"/simulation/runs/{second['run_id']}/results").status_code == 200


def test_results_reject_unknown_and_malformed_ids():
    client = TestClient(create_app())
    assert client.get("/simulation/runs/invalid/results").status_code == 422
    assert client.get(f"/simulation/runs/{'0' * 64}/results").status_code == 404


def test_incomplete_cached_data_returns_a_controlled_error(monkeypatch):
    service = SimulationRunService(load_station_layouts())
    run_id = "a" * 64
    service._cache[run_id] = {"run_id": run_id}
    monkeypatch.setattr(main, "SimulationRunService", lambda layouts: service)
    response = TestClient(create_app()).get(f"/simulation/runs/{run_id}/results")
    assert response.status_code == 500
    assert response.json()["detail"] == "Cached run results are invalid"
