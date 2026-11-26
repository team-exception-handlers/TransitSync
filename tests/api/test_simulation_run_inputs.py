# AI contribution: 50% or more AI-generated
"""Check the inputs the run endpoint gives each strategy.

Several demo bugs came from these inputs rather than from the strategies:
headway targets were whole-day medians (300 s) while the scenario hour runs
every 180 s, so every train was held; only adaptive saw incoming transfer
groups, so connection protection and rolling horizon never held anyone;
trains ran empty, so holding looked free; and metro trips had no later stop,
so transfer passengers could never board.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.simulation_run as simulation_run
from api.main import create_app
from api.network_data import load_reference_network
from api.station_layout import load_station_layouts
from simulator.control.observation_builder import ObservationBuilder
from simulator.control.strategies import STRATEGIES
from simulator.engine.random_streams import StreamManager
from simulator.scenario_parameters import ScenarioParameters

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
        "transfer_volume": 21,
    }
    if strategy == "adaptive":
        settings["irregularity_threshold"] = 0.25

    response = TestClient(create_app()).post("/simulation/run", json=settings)

    assert response.status_code == 200
    assert source_counts == [1]


def test_connection_protection_holds_trains_for_transfers_in_a_full_run(monkeypatch):
    """Before the fix this run had zero holds because no transfers were seen.

    With nobody on board, any caught transfer makes a hold worthwhile, so holds
    show the transfers reached the strategy. Every hold must still respect the
    requested maximum hold.
    """
    settings = {
        "onboard_load": 0,
        "connection_id": "mcgill-rem-green",
        "strategy": "connection_protection",
        "max_hold_time": 60,
        "error_magnitude": 0,
        "transfer_volume": 42,
    }

    response = TestClient(create_app()).post("/simulation/run", json=settings)

    assert response.status_code == 200
    applied = [decision["applied_s"] for decision in response.json()["decisions"]]
    assert any(hold_s > 0 for hold_s in applied)
    assert all(0 <= hold_s <= 60 for hold_s in applied)


def _stop_trip(trip_id: str, platform_id: str, arrival_s: float, departure_s: float):
    """Build a one-visit timetable trip, like the metro trips in the network."""
    visit = SimpleNamespace(
        stop_id="32",
        platform_id=platform_id,
        arrival_s=arrival_s,
        departure_s=departure_s,
    )
    return SimpleNamespace(
        feed_id="feed", trip_id=trip_id, route_id="1", visits=(visit,)
    )


def _route_trip(
    trip_id: str,
    route_id: str,
    platform_id: str,
    relative_departure_s: float,
    direction_id: int = 0,
):
    """Build one single-stop trip with a 30-second dwell at the chosen platform."""
    arrival_s = START_S + relative_departure_s - 30
    visit = SimpleNamespace(
        stop_id="32",
        platform_id=platform_id,
        arrival_s=arrival_s,
        departure_s=arrival_s,
    )
    return SimpleNamespace(
        feed_id="stm",
        trip_id=trip_id,
        route_id=route_id,
        direction_id=direction_id,
        visits=(visit,),
    )


def test_trains_carry_the_onboard_load_and_connecting_trips_ride_on(monkeypatch):
    """Only a trip ending at the connecting platform gets the onward stop.

    It reuses that platform and is reached one whole run after leaving, so it
    lies after the hour ends; every train starts with the scenario's onboard load.
    """
    monkeypatch.setattr(simulation_run, "scenario_start_clock_s", lambda _: START_S)
    trips = (
        _stop_trip("green", "green_mcgill_0", START_S + 60, START_S + 90),
        _stop_trip("other", "green_mcgill_1", START_S + 60, START_S + 90),
    )
    network = SimpleNamespace(trips_for_date=lambda _: trips)
    scenario = SimpleNamespace(
        service_date=None,
        duration_s=DURATION_S,
        parameters=ScenarioParameters(onboard_load=250),
    )

    trains = simulation_run._build_trains(network, scenario, "green_mcgill_0")

    by_trip = {train.id: train for train in trains}
    stop, onward = by_trip["feed:green"].schedule
    assert (onward.station_id, onward.platform_id) == (
        "green_mcgill_0-onward",
        "green_mcgill_0",
    )
    assert onward.arrival_s == stop.departure_s + DURATION_S > DURATION_S
    assert len(by_trip["feed:other"].schedule) == 1
    assert {train.onboard_load for train in trains} == {250}


def test_transfer_passengers_board_the_connecting_train_in_a_full_run():
    """Before the onward stop every transfer passenger waited until the end."""
    settings = {
        "connection_id": "mcgill-rem-green",
        "strategy": "no_control",
        "error_magnitude": 0,
        "transfer_volume": 42,
    }

    response = TestClient(create_app()).post("/simulation/run", json=settings)

    assert response.status_code == 200
    endings = {
        track["samples"][-1]["phase"] for track in response.json()["passenger_tracks"]
    }
    assert "boarded" in endings


def test_perfect_information_shows_no_gap_in_the_decision_estimates(monkeypatch):
    """Error magnitude 0 is the upper bound: what was seen equals the truth.

    Nobody on board makes holds frequent, so there are estimates to check.
    Each shown decision has exactly one estimates record, cut to its train.
    """
    settings = {
        "onboard_load": 0,
        "connection_id": "mcgill-rem-green",
        "strategy": "connection_protection",
        "max_hold_time": 60,
        "error_magnitude": 0,
        "transfer_volume": 84,
    }

    payload = TestClient(create_app()).post("/simulation/run", json=settings).json()

    decisions, estimates = payload["decisions"], payload["estimates"]
    assert decisions
    assert [(e["time_s"], e["train_id"]) for e in estimates] == [
        (d["time_s"], d["train_id"]) for d in decisions
    ]
    pairs = [
        value
        for record in estimates
        for item in (*record["trains"], *record["transfers"])
        for key, value in item.items()
        if key not in {"train_id", "group_id"}
    ]
    assert pairs
    assert all(pair["seen"] == pair["true"] for pair in pairs)


@pytest.mark.parametrize(
    ("preset", "expected_time", "expected_magnitude"),
    [
        ("platform_delay", 90.0, 75.0),
        ("line_suspension", 90.0, 75.0),
        ("uneven_headways", 90.0, 0.75),
    ],
)
def test_disruption_presets_validate_custom_time_and_magnitude(
    preset: str, expected_time: float, expected_magnitude: float
) -> None:
    """Every preset accepts the shared time and magnitude controls."""
    request = simulation_run.SimulationRunRequest(
        connection_id="mcgill-rem-green",
        disruption_preset=preset,
        disruption_time_s=expected_time,
        disruption_magnitude=expected_magnitude,
    )

    assert request.disruption_time_s == expected_time
    assert request.disruption_magnitude == expected_magnitude


def test_uneven_headways_rejects_magnitude_above_one_cv() -> None:
    """Prevent API requests from reaching the spacing model with an invalid CV."""
    with pytest.raises(
        ValueError,
        match="disruption_magnitude must be at most 1 as a coefficient of variation",
    ):
        simulation_run.SimulationRunRequest(
            connection_id="mcgill-rem-green",
            disruption_preset="uneven_headways",
            disruption_magnitude=1.01,
        )


def test_uneven_headways_perturbs_green_line_dispatch_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The configured start and CV perturb only later Green dispatch intervals."""
    monkeypatch.setattr(simulation_run, "scenario_start_clock_s", lambda _: START_S)
    green_one = _route_trip("green-one", "1", "green_mcgill_0", 90)
    green_two = _route_trip("green-two", "1", "green_mcgill_0", 390)
    green_three = _route_trip("green-three", "1", "green_mcgill_0", 690)
    green_reverse_one = _route_trip(
        "green-reverse-one", "1", "green_mcgill_1", 90, direction_id=1
    )
    green_reverse_two = _route_trip(
        "green-reverse-two", "1", "green_mcgill_1", 390, direction_id=1
    )
    green_reverse_three = _route_trip(
        "green-reverse-three", "1", "green_mcgill_1", 690, direction_id=1
    )
    green_after_horizon = _route_trip(
        "green-after-horizon", "1", "green_mcgill_0", 3990
    )
    rem = _route_trip("rem-one", "S1", "rem_mcgill_0", 150)
    network = SimpleNamespace(
        trips_for_date=lambda _: (
            green_one,
            green_two,
            green_three,
            green_reverse_one,
            green_reverse_two,
            green_reverse_three,
            green_after_horizon,
            rem,
        )
    )
    scenario = SimpleNamespace(
        service_date=None,
        duration_s=DURATION_S,
        parameters=ScenarioParameters(),
    )
    request = simulation_run.SimulationRunRequest(
        connection_id="mcgill-rem-green",
        disruption_preset="uneven_headways",
        disruption_time_s=300,
        disruption_magnitude=0.3,
    )
    trains = simulation_run._build_trains(
        network,
        scenario,
        "green_mcgill_0",
        request,
        StreamManager(42),
    )
    lower_magnitude_trains = simulation_run._build_trains(
        network,
        scenario,
        "green_mcgill_0",
        simulation_run.SimulationRunRequest(
            connection_id="mcgill-rem-green",
            disruption_preset="uneven_headways",
            disruption_time_s=300,
            disruption_magnitude=0.1,
        ),
        StreamManager(42),
    )
    preset_default_trains = simulation_run._build_trains(
        network,
        scenario,
        "green_mcgill_0",
        simulation_run.SimulationRunRequest(
            connection_id="mcgill-rem-green",
            disruption_preset="uneven_headways",
            disruption_time_s=300,
        ),
        StreamManager(42),
    )

    green_departures = {train.id: train.schedule[0].departure_s for train in trains}
    lower_departures = {
        train.id: train.schedule[0].departure_s for train in lower_magnitude_trains
    }
    preset_departures = {
        train.id: train.schedule[0].departure_s for train in preset_default_trains
    }
    assert green_departures["stm:green-one"] == 90.0
    assert green_departures["stm:green-two"] == 390.0
    assert green_departures["stm:green-three"] != 690.0
    assert green_departures["stm:green-reverse-one"] == 90.0
    assert green_departures["stm:green-reverse-two"] == 390.0
    assert green_departures["stm:green-reverse-three"] != 690.0
    assert green_departures["stm:green-three"] != lower_departures["stm:green-three"]
    assert green_departures["stm:green-after-horizon"] == 3990.0
    assert preset_departures == green_departures
    assert green_departures["stm:rem-one"] == 150.0


def test_line_suspension_targets_the_connection_metro_route_id() -> None:
    """The preset suspends route 1, not the display name \"green\"."""
    layout = load_station_layouts()["mcgill"]
    connection = next(
        item for item in layout.connections if item.id == "mcgill-rem-green"
    )
    request = simulation_run.SimulationRunRequest(
        connection_id=connection.id,
        disruption_preset="line_suspension",
        disruption_time_s=60,
        disruption_magnitude=600,
    )

    suspensions = simulation_run._line_suspensions(
        request,
        load_reference_network(),
        connection,
    )

    assert [(item.line_id, item.start_s, item.end_s) for item in suspensions] == [
        ("1", 60.0, 660.0)
    ]
