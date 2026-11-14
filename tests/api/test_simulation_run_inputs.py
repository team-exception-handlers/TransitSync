# AI contribution: 50% or more AI-generated
"""Check the inputs the run endpoint gives each strategy.

Two demo bugs came from these inputs rather than from the strategies: headway
targets were whole-day medians (300 s) while the scenario hour runs every
180 s, so every train was held; and only adaptive saw incoming transfer
groups, so connection protection and rolling horizon never held anyone.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.simulation_run as simulation_run
from api.main import create_app
from simulator.control.observation_builder import ObservationBuilder
from simulator.control.strategies import STRATEGIES
from simulator.engine.random_streams import StreamManager

# Scenario window used by the fake timetables: 07:00 for one hour
START_S = 25200
DURATION_S = 3600


def _trip(platform_id: str, *departures: float, outgoing: bool = True):
    """Build a trip with one visit per departure clock time on one platform."""
    return SimpleNamespace(
        visits=tuple(
            SimpleNamespace(
                platform_id=platform_id,
                departure_s=departure_s,
                outgoing_passenger_service=outgoing,
            )
            for departure_s in departures
        )
    )


def _targets(monkeypatch: pytest.MonkeyPatch, *trips) -> dict[str, float]:
    """Run ``_headway_targets`` on fake trips for platforms "A" and "B"."""
    monkeypatch.setattr(simulation_run, "scenario_start_clock_s", lambda _: START_S)
    network = SimpleNamespace(
        trips_for_date=lambda _: trips,
        platforms=[SimpleNamespace(platform_id="A"), SimpleNamespace(platform_id="B")],
    )
    scenario = SimpleNamespace(service_date=None, duration_s=DURATION_S)
    return simulation_run._headway_targets(network, scenario)


def test_headway_target_is_the_median_gap_inside_the_scenario_window(monkeypatch):
    """Peak trains every 180 s inside the hour, off-peak every 600 s outside.

    The whole-day median of these gaps would be 600 s; only the in-window
    departures 25200, 25380, 25560 and 25740 count, so the target is 180 s.
    """
    off_peak_before = _trip("A", 20000, 20600, 21200, 21800, 22400)
    peak = _trip("A", START_S, START_S + 180, START_S + 360, START_S + 540)
    off_peak_after = _trip("A", 29400, 30000, 30600, 31200, 31800)

    targets = _targets(monkeypatch, off_peak_before, peak, off_peak_after)

    assert targets["A"] == 180


def test_window_edges_and_non_service_visits_fall_back_to_300_s(monkeypatch):
    """The window is [start, start + duration): the end is excluded.

    Platform A has one departure at the start and one exactly at the end, so
    only one counts and it gets the 300 s fallback despite many visits outside.
    Platform B's in-window visits carry no outgoing passengers, so they are
    skipped and B also falls back.
    """
    edges = _trip("A", START_S, START_S + DURATION_S, 30000, 30120, 30240)
    no_service = _trip("B", START_S + 60, START_S + 120, outgoing=False)

    targets = _targets(monkeypatch, edges, no_service)

    assert targets == {"A": 300.0, "B": 300.0}


@pytest.mark.parametrize("strategy", STRATEGIES.names())
def test_every_strategy_observes_the_incoming_transfer_groups(monkeypatch, strategy):
    """Each strategy's decision pipeline gets the run's transfer component.

    The simulation itself is stubbed after component construction, so this
    checks wiring only; the full run below checks the effect on holds.
    """
    source_counts = []

    class RecordingBuilder(ObservationBuilder):
        def __init__(self, transfer_sources=()):
            sources = tuple(transfer_sources)
            source_counts.append(len(sources))
            super().__init__(sources)

    def fake_run_scenario(scenario, _streams, component_factory, output_dir: Path):
        component_factory(scenario, StreamManager(42))
        events_path = output_dir / "events.jsonl"
        decisions_path = output_dir / "decisions.jsonl"
        events_path.write_text("", encoding="utf-8")
        decisions_path.write_text("", encoding="utf-8")
        return SimpleNamespace(events_path=events_path, decisions_path=decisions_path)

    monkeypatch.setattr(simulation_run, "ObservationBuilder", RecordingBuilder)
    monkeypatch.setattr(simulation_run, "run_scenario", fake_run_scenario)
    settings = {
        "connection_id": "mcgill-rem-green",
        "strategy": strategy,
        "error_magnitude": 0,
        "passenger_flow": "Low",
    }
    if strategy == "adaptive":
        settings["irregularity_threshold"] = 0.25

    response = TestClient(create_app()).post("/simulation/run", json=settings)

    assert response.status_code == 200
    assert source_counts == [1]


def test_connection_protection_holds_trains_for_transfers_in_a_full_run():
    """Before the fix this run had zero holds because no transfers were seen.

    Every hold must still respect the requested maximum hold.
    """
    settings = {
        "connection_id": "mcgill-rem-green",
        "strategy": "connection_protection",
        "max_hold_time": 60,
        "error_magnitude": 0,
        "passenger_flow": "Normal",
    }

    response = TestClient(create_app()).post("/simulation/run", json=settings)

    assert response.status_code == 200
    applied = [decision["applied_s"] for decision in response.json()["decisions"]]
    assert any(hold_s > 0 for hold_s in applied)
    assert all(0 <= hold_s <= 60 for hold_s in applied)
