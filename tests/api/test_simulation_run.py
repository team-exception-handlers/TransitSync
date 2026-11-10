# AI contribution: 50% or more AI-generated
"""Contract, validation, and cache tests for simulation-run requests.

Tests use the committed schedules and station layouts; no external service is
required to execute a complete one-hour simulation.
"""

import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.simulation_run as simulation_run
from api.main import create_app
from api.simulation_run import SimulationRunRequest, SimulationRunService
from api.station_layout import load_station_layouts
from api.station_view import SimulationRunResponse
from simulator.control.strategies import STRATEGIES
from simulator.control.strategies.connection_protection import (
    ConnectionProtectionStrategy,
)
from simulator.engine.random_streams import StreamManager

RUN_SETTINGS = {
    "connection_id": "mcgill-rem-green",
    "strategy": "schedule_based",
    "max_hold_time": 120,
    "error_magnitude": 1,
    "passenger_flow": "Normal",
    "disruption_enabled": False,
}


def _route_points(payload: dict, connection_id: str) -> list[dict[str, float]]:
    """Return the feeder platform, corridor path and connecting platform points."""
    connection = next(
        item for item in payload["connections"] if item["id"] == connection_id
    )
    corridor = next(
        item for item in payload["corridors"] if item["id"] == connection["corridor_id"]
    )
    platforms = {item["platform_id"]: item for item in payload["platforms"]}
    return [
        platforms[connection["from_platform_id"]]["position"],
        *corridor["path"],
        platforms[connection["to_platform_id"]]["position"],
    ]


def _distance_to_route(point: dict, route: list[dict[str, float]]) -> float:
    """Return the shortest distance in pixels from a point to the route polyline."""
    best = float("inf")
    for start, end in zip(route, route[1:], strict=False):
        dx, dy = end["x"] - start["x"], end["y"] - start["y"]
        length_squared = dx * dx + dy * dy
        fraction = 0.0
        if length_squared > 0:
            projected = (point["x"] - start["x"]) * dx + (point["y"] - start["y"]) * dy
            fraction = min(1.0, max(0.0, projected / length_squared))
        nearest_x = start["x"] + fraction * dx
        nearest_y = start["y"] + fraction * dy
        best = min(best, math.hypot(point["x"] - nearest_x, point["y"] - nearest_y))
    return best


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
    # Every position is on the platform-corridor-platform route, so markers
    # follow the corridor instead of cutting across the map (US-3.1).
    route = _route_points(payload, connection_id)
    off_route = [
        sample["position"]
        for track in payload["passenger_tracks"]
        for sample in track["samples"]
        if _distance_to_route(sample["position"], route) > 1e-6
    ]
    assert off_route == []


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

    def count_runs(settings: SimulationRunRequest) -> SimulationRunResponse:
        nonlocal run_count
        run_count += 1
        return run_uncached(settings)

    monkeypatch.setattr(service, "_run_uncached", count_runs)
    first = service.run(request)
    first.passenger_tracks.clear()

    second = service.run(request)

    assert run_count == 1
    assert second.passenger_tracks
    assert second.passenger_tracks is not first.passenger_tracks


def test_run_service_shares_duplicate_work_without_serializing_other_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deduplicate matching requests while allowing different runs in parallel.

    Two distinct settings must reach the simulator together, while a duplicate
    request waits on its own in-flight result rather than starting another run.
    """
    layout = load_station_layouts()["mcgill"]
    response = SimulationRunResponse(
        **layout.model_dump(),
        schema_version=1,
        start_clock_s=0,
        duration_s=3600,
        passenger_tracks=[],
        train_events=[],
        decisions=[],
        rules=[],
        operating_rules={
            "max_hold_time": 300,
            "min_safe_gap": 60,
            "rule_action_map": {
                "max_hold_exceeded": "CLAMP",
                "headway_violation": "REFUSE",
                "one_hop_violation": "REFUSE",
            },
        },
    )
    service = SimulationRunService({"mcgill": layout})
    barrier = Barrier(2)
    count_lock = Lock()
    run_count = 0

    def run_uncached(_: SimulationRunRequest) -> SimulationRunResponse:
        nonlocal run_count
        with count_lock:
            run_count += 1
        barrier.wait(timeout=10)
        return response.model_copy(deep=True)

    monkeypatch.setattr(service, "_run_uncached", run_uncached)
    no_control = SimulationRunRequest.model_validate(
        {**RUN_SETTINGS, "strategy": "no_control"}
    )
    schedule_based = SimulationRunRequest.model_validate(
        {**RUN_SETTINGS, "strategy": "schedule_based"}
    )

    with ThreadPoolExecutor(max_workers=3) as executor:
        no_control_runs = [
            executor.submit(service.run, no_control),
            executor.submit(service.run, no_control),
        ]
        schedule_run = executor.submit(service.run, schedule_based)
        results = [run.result(timeout=15) for run in no_control_runs]
        results.append(schedule_run.result(timeout=15))

    assert run_count == 2
    assert all(result.interchange.id == "mcgill" for result in results)


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
    queued_samples = [
        sample
        for track in high_flow["passenger_tracks"]
        for sample in track["samples"]
        if sample["phase"] == "queued"
    ]
    assert queued_samples
    # The corridor's capacity limit is at its metro end (US-3.1 path fix).
    corridor_path = high_flow["corridors"][0]["path"]
    bottleneck = corridor_path[-1]
    assert all(sample["position"] == bottleneck for sample in queued_samples)
    walking_positions = [
        sample["position"]
        for track in high_flow["passenger_tracks"]
        for sample in track["samples"]
        if sample["phase"] == "walking"
    ]
    # Walks follow the corridor, so every bend in it is a sampled position.
    assert all(point in walking_positions for point in corridor_path)
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
        {"error_magnitude": 1000},
        {"strategy": "adaptive"},
        {"strategy": "adaptive", "irregularity_threshold": -0.1},
        {"strategy": "no_control", "irregularity_threshold": 0.25},
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


@pytest.mark.parametrize("strategy", STRATEGIES.names())
def test_every_registered_strategy_builds_through_the_api(
    monkeypatch: pytest.MonkeyPatch,
    strategy: str,
) -> None:
    """Keep each registry strategy compatible with endpoint settings and wiring.

    The real run is stubbed after component construction to avoid expensive
    planner work; the normal endpoint integration test covers full simulation.
    """

    def fake_run_scenario(
        scenario,
        _stream_factory,
        component_factory,
        output_dir: Path,
    ) -> SimpleNamespace:
        component_factory(scenario, StreamManager(42))
        events_path = output_dir / "events.jsonl"
        events_path.write_text("", encoding="utf-8")
        # The real RunResult always has a decision log; the API reads it (#60).
        decisions_path = output_dir / "decisions.jsonl"
        decisions_path.write_text("", encoding="utf-8")
        return SimpleNamespace(events_path=events_path, decisions_path=decisions_path)

    monkeypatch.setattr(simulation_run, "run_scenario", fake_run_scenario)
    client = TestClient(create_app())

    request_settings = {
        **RUN_SETTINGS,
        "strategy": strategy,
        "passenger_flow": "Low",
        "error_magnitude": 0,
    }
    if strategy == "adaptive":
        request_settings["irregularity_threshold"] = 0.25
    response = client.post("/simulation/run", json=request_settings)

    assert response.status_code == 200
    assert response.json()["interchange"]["id"] == "mcgill"


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


def test_run_service_rejects_connection_id_shared_by_two_interchanges() -> None:
    """Refuse a catalog where one connection ID belongs to two interchanges.

    The service shares the connection-data index, so a repeated ID fails at
    construction instead of silently resolving to whichever layout comes first.
    """
    mcgill = load_station_layouts()["mcgill"]

    with pytest.raises(ValueError, match="duplicate connection ID: 'mcgill-rem-green'"):
        SimulationRunService({"mcgill": mcgill, "mcgill-copy": mcgill})


def test_adaptive_connection_mode_receives_incoming_transfers(monkeypatch):
    """Exercise the real API factory and observe its connection delegate."""
    transfer_counts = []
    original_evaluate = ConnectionProtectionStrategy.evaluate

    def observe(self, observation):
        transfer_counts.append(len(observation.incoming_transfers))
        return original_evaluate(self, observation)

    monkeypatch.setattr(ConnectionProtectionStrategy, "evaluate", observe)
    response = TestClient(create_app()).post(
        "/simulation/run",
        json={
            **RUN_SETTINGS,
            "strategy": "adaptive",
            "irregularity_threshold": 10.0,
            "error_magnitude": 0,
        },
    )

    assert response.status_code == 200
    assert max(transfer_counts, default=0) > 0


def test_adaptive_run_returns_mode_switches_for_the_selected_connection() -> None:
    """Expose adaptive mode switches so the timeline can mark them (#60).

    Adaptive switches to headway regulation exactly when the recorded
    irregularity is above the threshold, and back otherwise, so each record's
    direction can be checked against its own numbers.
    """
    settings = {
        **RUN_SETTINGS,
        "strategy": "adaptive",
        "irregularity_threshold": 0.25,
    }
    payload = TestClient(create_app()).post("/simulation/run", json=settings).json()
    connection = payload["connections"][0]
    shown = {connection["from_platform_id"], connection["to_platform_id"]}
    switches = payload["mode_switches"]
    times = [switch["time_s"] for switch in switches]

    assert switches
    assert {switch["platform_id"] for switch in switches} <= shown
    assert times == sorted(times)
    assert all(0 <= time_s <= payload["duration_s"] for time_s in times)
    for switch in switches:
        above = switch["service_irregularity"] > switch["irregularity_threshold"]
        expected = "headway_regulation" if above else "connection_protection"
        assert switch["to_mode"] == expected
        assert switch["from_mode"] != switch["to_mode"]


def test_non_adaptive_run_returns_no_mode_switches() -> None:
    """Only adaptive switches mode, so other strategies return an empty list."""
    response = TestClient(create_app()).post("/simulation/run", json=RUN_SETTINGS)

    assert response.status_code == 200
    assert response.json()["mode_switches"] == []
