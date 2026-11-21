# AI contribution: 50% or more AI-generated
"""Exercise the results endpoint through the same cache used for playback."""

from fastapi.testclient import TestClient

import api.main as main
import api.simulation_run as simulation_run
from api.main import create_app
from api.simulation_run import SimulationRunService
from api.station_layout import load_station_layouts


def test_results_follow_the_requested_run_and_its_cache_lifetime(monkeypatch):
    monkeypatch.setattr(simulation_run, "MAX_CACHED_RUNS", 1)
    client = TestClient(create_app())
    settings = {"connection_id": "mcgill-rem-green"}
    previous_id = None
    for strategy in ["no_control", "connection_protection"]:
        response = client.post(
            "/simulation/run", json={**settings, "strategy": strategy}
        )
        assert response.status_code == 200
        playback = response.json()
        run_id = playback["run_id"]
        with monkeypatch.context() as cached_only:

            def unexpected_run(*args):
                raise AssertionError("Reading cached results reran the simulation")

            cached_only.setattr(SimulationRunService, "_run_uncached", unexpected_run)
            if strategy == "no_control":
                assert (
                    client.post("/simulation/run", json=settings).json()["run_id"]
                    == run_id
                )
            results = client.get(f"/simulation/runs/{run_id}/results")
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
            if previous_id:
                assert previous_id != run_id
                assert (
                    client.get(f"/simulation/runs/{previous_id}/results").status_code
                    == 404
                )
        previous_id = run_id


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
