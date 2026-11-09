# AI contribution: 50% or more AI-generated
"""Exercise connection protection through the real simulation endpoint (#51).

Keep the simulator and component construction real. Observe the registry and
passenger routes to verify settings reach the strategy used by the train engine.
The three committed demo destinations have service gaps of 300, 300 and 360 s.
Expected gaps are fixed reference values rather than calls to the API's own
headway helper, so an incorrect platform lookup cannot validate itself.
"""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.simulation_run as simulation_run
from api.main import create_app
from simulator.control.strategies import STRATEGIES


@pytest.fixture(params=[(120, 30), (150, 45)])
def observed_components(monkeypatch, request):
    """Observe real components with default or non-default route walking times.

    Changing the route catches a controller that silently uses API constants.
    Every spy delegates to the actual constructor; no simulation is stubbed.
    """
    strategies = []
    routes = []
    build = STRATEGIES.build
    transfer_component = simulation_run.TransferComponent
    build_route = simulation_run._build_transfer_route
    mean_s, min_s = request.param

    def observe_strategy(name, **settings):
        strategy = build(name, **settings)
        strategies.append(strategy)
        return strategy

    def observe_transfers(configured_routes, streams):
        routes.extend(configured_routes)
        return transfer_component(configured_routes, streams)

    def configured_route(*args):
        return replace(build_route(*args), walking_mean_s=mean_s, walking_min_s=min_s)

    monkeypatch.setattr(STRATEGIES, "build", observe_strategy)
    monkeypatch.setattr(simulation_run, "TransferComponent", observe_transfers)
    monkeypatch.setattr(simulation_run, "_build_transfer_route", configured_route)
    return SimpleNamespace(strategies=strategies, routes=routes)


@pytest.mark.parametrize(
    "connection_id, platform_id, headway_s",
    [
        (
            "gare_centrale_bonaventure-rem-orange",
            "orange_gare_centrale_bonaventure_0",
            300,
        ),
        ("mcgill-rem-green", "green_mcgill_0", 300),
        ("edouard_montpetit-rem-blue", "blue_edouard_montpetit_0", 360),
    ],
)
@pytest.mark.parametrize("max_hold_s", [5, 120])
def test_connection_protection_runs_with_destination_settings(
    observed_components, connection_id, platform_id, headway_s, max_hold_s
):
    """Run each interchange with a normal grid and its smallest allowed bound.

    The strategy must use only its destination's service headway and the walking
    parameters used to generate passengers. Audit records prove decisions ran,
    even if the best choice was no hold. Safety limits still cap applied holds.
    The 5 s bound leaves one positive candidate on the default grid; 120 s
    exercises a larger search. Blue's 360 s gap catches a hard-coded 300 s
    headway that would otherwise pass for the orange and green destinations.
    """
    client = TestClient(create_app())
    response = client.post(
        "/simulation/run",
        json={
            "connection_id": connection_id,
            "strategy": "connection_protection",
            "max_hold_time": max_hold_s,
            "error_magnitude": 0,
            "passenger_flow": "Normal",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["train_events"]
    assert payload["passenger_tracks"]
    [strategy] = observed_components.strategies
    [route] = observed_components.routes
    assert strategy.headways_s == {platform_id: headway_s}
    search = strategy.searches[platform_id]
    assert search.walking.mean_s == route.walking_mean_s
    assert search.walking.min_s == route.walking_min_s
    assert search.settings.max_hold_s == max_hold_s
    records = strategy.decision_records()
    assert records
    assert {record["platform_id"] for record in records} == {platform_id}
    assert all(record["inputs"]["headway_s"] == headway_s for record in records)
    assert all(record["chosen_hold_s"] <= max_hold_s for record in records)
    assert payload["operating_rules"]["max_hold_time"] == max_hold_s
    assert all(d["applied_s"] <= max_hold_s for d in payload["decisions"])


def test_connection_protection_is_reproducible_across_api_instances():
    """Compare complete responses from independent seeded runs, bypassing caches.

    Each application owns a fresh service, so the second response must come
    from another simulation. Nonzero prediction error exercises seeded draws
    as well as passenger generation and hold decisions.
    """
    settings = {
        "connection_id": "mcgill-rem-green",
        "strategy": "connection_protection",
        "max_hold_time": 120,
        "error_magnitude": 1,
        "passenger_flow": "Normal",
    }
    first = TestClient(create_app()).post("/simulation/run", json=settings)
    second = TestClient(create_app()).post("/simulation/run", json=settings)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
