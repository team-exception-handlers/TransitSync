# AI contribution: 50% or more AI-generated
"""Scenario parameters and presets reach the simulation (#258, #259, #265).

The simulator run itself is replaced by a stub that only builds the
components, so each test checks the exact values handed to the engine
without running a full simulated hour.
"""

from datetime import date, time
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.simulation_run as simulation_run
from api.main import create_app
from simulator.engine.random_streams import StreamManager
from simulator.scenario import PRESET_SETTINGS
from simulator.scenario_parameters import ScenarioParameters

CONNECTION = "mcgill-rem-green"
FEEDER, CONNECTING = "rem_mcgill_0", "green_mcgill_0"
# Scheduled REM gap at McGill in the 07:00 window, in seconds
REM_HEADWAY_S = 210.0


@pytest.fixture
def built(monkeypatch):
    """Record the scenario, transfer route and trains of each stubbed run."""
    captured = {}
    build_components = simulation_run._build_components

    def recording_build(scenario, *args):
        transfers, trains = build_components(scenario, *args)
        captured["scenario"] = scenario
        captured["route"] = next(iter(transfers._routes.values()))
        captured["trains"] = list(trains.trains.values())
        return transfers, trains

    def fake_run_scenario(scenario, _streams, component_factory, output_dir: Path):
        component_factory(scenario, StreamManager(scenario.master_seed))
        for name in ("events.jsonl", "decisions.jsonl"):
            (output_dir / name).write_text("", encoding="utf-8")
        return SimpleNamespace(
            events_path=output_dir / "events.jsonl",
            decisions_path=output_dir / "decisions.jsonl",
        )

    monkeypatch.setattr(simulation_run, "_build_components", recording_build)
    monkeypatch.setattr(simulation_run, "run_scenario", fake_run_scenario)
    return captured


def _run(**settings):
    body = {"connection_id": CONNECTION, **settings}
    return TestClient(create_app()).post("/simulation/run", json=body)


def _connecting_departures(trains):
    return sorted(
        stop.departure_s
        for train in trains
        for stop in train.schedule[:1]
        if stop.platform_id == CONNECTING
    )


def test_omitted_parameters_run_with_the_scenario_defaults(built):
    assert _run().status_code == 200
    scenario = built["scenario"]
    assert scenario.parameters == ScenarioParameters()
    assert scenario.operating_rules.max_hold_time == 300.0
    assert scenario.control.hold_search.max_hold_s == 300.0


def test_each_requested_value_reaches_the_engine(built):
    response = _run(
        transfer_volume=70,
        train_headway_s=240,
        onboard_load=450,
        walking_mean_s=150,
        max_hold_time=60,
    )
    assert response.status_code == 200
    route, trains = built["route"], built["trains"]
    # M = 70 per 210 s REM gap: 70 * 60 / 210 = 20 passengers per minute
    assert route.demand_profile.periods[0].passengers_per_minute == pytest.approx(20)
    assert route.walking_mean_s == 150.0
    assert {train.onboard_load for train in trains} == {450}
    departures = _connecting_departures(trains)
    assert {b - a for a, b in pairwise(departures)} == {240.0}
    # The hold cap is applied in the search and in the safety rules
    assert built["scenario"].operating_rules.max_hold_time == 60.0
    assert built["scenario"].control.hold_search.max_hold_s == 60.0


def test_default_transfer_volume_gives_sixty_per_rem_train(built):
    assert _run().status_code == 200
    rate = built["route"].demand_profile.periods[0].passengers_per_minute
    # 60 per train over a 210 s gap; one gap of demand is 60 passengers
    assert rate * REM_HEADWAY_S / 60 == pytest.approx(60)


def test_chosen_frequency_is_the_connection_protection_gap(built):
    response = _run(strategy="connection_protection", train_headway_s=300)
    assert response.status_code == 200
    headways = built["scenario"].control.connection_headways_s
    assert dict(headways) == {CONNECTING: 300.0}


def test_uneven_headways_still_perturbs_a_re_timed_line(built):
    response = _run(train_headway_s=240, disruption_preset="uneven_headways")
    assert response.status_code == 200
    departures = _connecting_departures(built["trains"])
    gaps = [b - a for a, b in pairwise(departures)]
    assert any(gap != 240.0 for gap in gaps)


def test_preset_sets_the_window_and_its_conditions(built):
    response = _run(preset="sunday_morning")
    assert response.status_code == 200
    scenario = built["scenario"]
    # The reference network's Sunday and the preset's 10:00 start
    assert scenario.service_date == date(2026, 10, 11)
    assert scenario.start_time == time(10, 0)
    preset = PRESET_SETTINGS["sunday_morning"]
    assert scenario.parameters == ScenarioParameters(**preset["parameters"])
    assert scenario.operating_rules.max_hold_time == preset["max_hold_time"]


def test_a_requested_value_overrides_the_preset(built):
    response = _run(preset="weekday_afternoon", onboard_load=10, max_hold_time=45)
    assert response.status_code == 200
    scenario = built["scenario"]
    assert scenario.start_time == time(16, 0)
    assert scenario.parameters.onboard_load == 10
    assert scenario.operating_rules.max_hold_time == 45.0


@pytest.mark.parametrize(
    ("settings", "field"),
    [
        ({"preset": "holiday"}, "preset"),
        ({"transfer_volume": -1}, "transfer_volume"),
        ({"transfer_volume": 60.5}, "transfer_volume"),
        ({"train_headway_s": 125}, "train_headway_s"),
        ({"onboard_load": 801}, "onboard_load"),
        ({"walking_mean_s": 30}, "walking_mean_s"),
        ({"max_hold_time": 0}, "max_hold_time"),
        ({"passenger_flow": "High"}, "passenger_flow"),
    ],
)
def test_invalid_values_return_422_naming_the_field(settings, field):
    response = _run(**settings)
    assert response.status_code == 422
    locations = [error["loc"] for error in response.json()["detail"]]
    assert ["body", field] in [list(loc[:2]) for loc in locations]


def test_presets_endpoint_lists_every_preset_with_all_five_values():
    response = TestClient(create_app()).get("/scenario/presets")
    assert response.status_code == 200
    presets = response.json()
    assert [preset["name"] for preset in presets] == list(PRESET_SETTINGS)
    morning = presets[0]
    assert morning["label"] == "Weekday morning peak"
    assert morning["start_time"] == "07:00:00"
    assert set(morning["conditions"]) == {
        "transfer_volume",
        "train_headway_s",
        "onboard_load",
        "walking_mean_s",
        "max_hold_time",
    }
    # Each listed value is the one a run with that preset uses
    expected = ScenarioParameters(**PRESET_SETTINGS["weekday_morning"]["parameters"])
    assert morning["conditions"]["onboard_load"] == expected.onboard_load


def test_presets_endpoint_fails_loudly_on_a_bad_preset(monkeypatch):
    broken = {
        **PRESET_SETTINGS,
        "weekday_morning": {
            **PRESET_SETTINGS["weekday_morning"],
            "parameters": {"onboard_load": 5000},
        },
    }
    monkeypatch.setattr("api.scenario_presets.PRESET_SETTINGS", broken)
    with pytest.raises(ValueError, match=r"parameters\.onboard_load"):
        TestClient(create_app()).get("/scenario/presets")
