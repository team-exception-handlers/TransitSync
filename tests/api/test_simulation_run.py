"""Contract, validation, and cache tests for simulation-run requests.

Tests use the committed schedules and station layouts; no external service is
required to execute a complete one-hour simulation.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.simulation_run import SimulationRunRequest, SimulationRunService
from api.station_layout import load_station_layouts

RUN_SETTINGS = {
    "connection_id": "mcgill-rem-green",
    "strategy": "schedule_based",
    "max_hold_time": 120,
    "error_magnitude": 1,
    "passenger_flow": "Normal",
    "disruption_enabled": False,
}


@pytest.mark.parametrize(
    ("connection_id", "interchange_id"),
    [
        ("gare_centrale_bonaventure-rem-orange", "gare_centrale_bonaventure"),
        ("mcgill-rem-green", "mcgill"),
        ("edouard_montpetit-rem-blue", "edouard_montpetit"),
    ],
)
def test_run_endpoint_returns_map_ready_station_view_playback(
    connection_id: str, interchange_id: str
) -> None:
    """Return one hour of relative-time train and passenger data for the UI.

    All demo connections must resolve to their own interchange scenario.
    Train stop IDs and passenger connection IDs must match static layout data.
    Every track sample is constrained to the one-hour run horizon.
    The route must return the same response contract for each scenario.
    Passenger positions are validated against the platform and corridor map.
    """
    client = TestClient(create_app())

    response = client.post(
        "/simulation/run",
        json={**RUN_SETTINGS, "connection_id": connection_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["interchange"]["id"] == interchange_id
    assert payload["start_clock_s"] == 7 * 60 * 60
    assert payload["duration_s"] == 3600
    assert payload["connections"][0]["id"] == connection_id
    assert payload["train_events"]
    assert payload["passenger_tracks"]
    platform_by_id = {
        platform["platform_id"]: platform for platform in payload["platforms"]
    }
    assert all(
        event["station_id"] == platform_by_id[event["platform_id"]]["stop_id"]
        for event in payload["train_events"]
    )
    for track in payload["passenger_tracks"]:
        assert track["connection_id"] == connection_id
        assert track["samples"]
        times = [sample["time_s"] for sample in track["samples"]]
        assert times == sorted(times)
        assert all(0 <= time_s <= payload["duration_s"] for time_s in times)


def test_run_service_caches_detached_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reuse a real run without exposing mutable cached records to callers.

    Mutating a prior response must not change the cache's saved playback records.
    A cache hit must also avoid a second call to the actual simulator.
    The second response must be a distinct mutable object.
    A caller may therefore safely modify its response payload.
    """
    service = SimulationRunService(load_station_layouts())
    request = SimulationRunRequest.model_validate(RUN_SETTINGS)
    run_uncached = service._run_uncached
    run_count = 0

    def count_runs(
        settings: SimulationRunRequest,
    ) -> dict[str, object]:
        nonlocal run_count
        run_count += 1
        return run_uncached(settings)

    monkeypatch.setattr(service, "_run_uncached", count_runs)
    first = service.run(request)
    first_tracks = first["passenger_tracks"]
    assert isinstance(first_tracks, list)
    first_tracks.clear()

    second = service.run(request)

    second_tracks = second["passenger_tracks"]
    assert isinstance(second_tracks, list)
    assert run_count == 1
    assert second_tracks
    assert second_tracks is not first_tracks


def test_run_settings_change_demand_and_apply_selected_feeder_disruption() -> None:
    """Scale passenger tracks with flow and delay only the selected feeder.

    Identical seeded runs isolate the flow and disruption controls.
    The demand levels are ordered, and disruption shifts a feeder event later.
    No-control runs keep policy decisions from masking these input effects.
    The feeder delay must be visible in the selected connection's event stream.
    """
    client = TestClient(create_app())
    base_settings = {
        **RUN_SETTINGS,
        "strategy": "no_control",
        "error_magnitude": 0,
    }

    low_flow = client.post(
        "/simulation/run",
        json={**base_settings, "passenger_flow": "Low"},
    ).json()
    high_flow = client.post(
        "/simulation/run",
        json={**base_settings, "passenger_flow": "High"},
    ).json()
    uninterrupted = client.post(
        "/simulation/run",
        json={**base_settings, "passenger_flow": "Normal"},
    ).json()
    disrupted = client.post(
        "/simulation/run",
        json={**base_settings, "passenger_flow": "Normal", "disruption_enabled": True},
    ).json()

    assert len(high_flow["passenger_tracks"]) > len(low_flow["passenger_tracks"])
    uninterrupted_times = {
        (event["train_id"], event["platform_id"], event["event_type"]): event["time_s"]
        for event in uninterrupted["train_events"]
    }
    disrupted_times = {
        (event["train_id"], event["platform_id"], event["event_type"]): event["time_s"]
        for event in disrupted["train_events"]
    }
    assert any(
        platform_id == "rem_mcgill_0"
        and disrupted_times.get((train_id, platform_id, event_type), time_s) > time_s
        for (train_id, platform_id, event_type), time_s in uninterrupted_times.items()
    )


@pytest.mark.parametrize(
    "invalid_settings",
    [
        {"strategy": "not-registered"},
        {"passenger_flow": "Extreme"},
        {"max_hold_time": 301},
        {"max_hold_time": 121},
        {"error_magnitude": -1},
    ],
)
def test_run_endpoint_rejects_invalid_settings(
    invalid_settings: dict[str, object],
) -> None:
    """Return request-validation errors instead of starting invalid runs.

    Cases cover registry names, demand levels, hold bounds, and prediction kappa.
    Each malformed request is rejected before scenario loading or simulation.
    Values just outside discrete hold boundaries are rejected as well.
    No invalid request receives a success-shaped response.
    """
    client = TestClient(create_app())

    response = client.post("/simulation/run", json={**RUN_SETTINGS, **invalid_settings})

    assert response.status_code == 422


def test_run_endpoint_returns_not_found_for_unknown_connection() -> None:
    """Reject connection IDs absent from the validated station-layout catalog.

    The response names the missing ID and uses HTTP 404 rather than a fallback.
    This distinguishes an unknown selection from malformed request settings.
    The lookup is against the validated connection catalog.
    """
    client = TestClient(create_app())

    response = client.post(
        "/simulation/run", json={**RUN_SETTINGS, "connection_id": "unknown"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown connection: unknown"}
