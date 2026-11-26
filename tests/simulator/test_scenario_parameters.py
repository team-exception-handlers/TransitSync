# AI contribution: 50% or more AI-generated
"""Scenario demand and service parameters (#258): defaults, ranges, errors."""

import json
from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.scenario import (
    DatasetMetadata,
    ScenarioValidationError,
    load_scenario_json,
)
from simulator.scenario_parameters import (
    PARAMETER_RANGES,
    ParameterRange,
    ScenarioParameters,
    ScenarioParametersError,
    parse_scenario_parameters,
)


@pytest.fixture
def dataset():
    return DatasetMetadata(
        dataset_id="stm-rem-test",
        coverage_start=date(2026, 8, 24),
        coverage_end=date(2026, 12, 31),
        service_day_end_s_by_interchange={"mcgill": 92576},
        interchange_ids=frozenset({"mcgill"}),
    )


def load_with(dataset, parameters):
    values = {
        "dataset_id": dataset.dataset_id,
        "date": "2026-10-05",
        "start_time": "07:00",
        "interchanges": ["mcgill"],
        "parameters": parameters,
    }
    return load_scenario_json(json.dumps(values), {dataset.dataset_id: dataset})


def test_missing_object_gives_the_pre_258_defaults():
    # 300 on board and a 120 s mean walk were the run endpoint's constants
    assert parse_scenario_parameters(None) == ScenarioParameters(
        transfer_volume=60,
        train_headway_s=None,
        onboard_load=300,
        walking_mean_s=120.0,
    )


def test_scenario_file_values_reach_the_loaded_scenario(dataset):
    scenario = load_with(
        dataset,
        {
            "transfer_volume": 80,
            "train_headway_s": 240,
            "onboard_load": 450,
            "walking_mean_s": 150,
        },
    )
    assert scenario.parameters == ScenarioParameters(80, 240.0, 450, 150.0)
    # The manifest copy round-trips to the same values
    assert scenario.to_dict()["parameters"] == {
        "transfer_volume": 80,
        "train_headway_s": 240.0,
        "onboard_load": 450,
        "walking_mean_s": 150.0,
    }


@pytest.mark.parametrize(
    ("name", "low", "high"),
    [
        ("transfer_volume", 0, 200),
        ("train_headway_s", 120, 600),
        ("onboard_load", 0, 800),
        ("walking_mean_s", 45, 600),
    ],
)
def test_both_range_ends_are_accepted(name, low, high):
    assert getattr(parse_scenario_parameters({name: low}), name) == low
    assert getattr(parse_scenario_parameters({name: high}), name) == high


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ({"transfer_volume": -1}, "parameters.transfer_volume: must be between 0"),
        ({"transfer_volume": 201}, "parameters.transfer_volume: must be between"),
        ({"transfer_volume": 60.5}, "parameters.transfer_volume: expected a whole"),
        ({"train_headway_s": 90}, "parameters.train_headway_s: must be between 120"),
        ({"train_headway_s": 125}, "parameters.train_headway_s: .* steps of 30"),
        ({"onboard_load": 801}, "parameters.onboard_load: must be between 0 and 800"),
        ({"walking_mean_s": 30}, "parameters.walking_mean_s: must be between 45"),
        ({"walking_mean_s": True}, "parameters.walking_mean_s: expected a number"),
        ({"onboard_load": "300"}, "parameters.onboard_load: expected a number"),
        ({"walk_mean": 100}, "parameters.walk_mean: unknown field"),
    ],
)
def test_invalid_values_name_the_field(dataset, parameters, message):
    with pytest.raises(ScenarioValidationError, match=message):
        load_with(dataset, parameters)


def test_parameters_must_be_an_object():
    with pytest.raises(ScenarioParametersError, match="parameters: must be an object"):
        parse_scenario_parameters([60])


def test_null_headway_keeps_the_timetable():
    assert parse_scenario_parameters({"train_headway_s": None}).train_headway_s is None


def test_range_step_tolerates_binary_rounding():
    # 0.1 + 0.2 is 0.30000000000000004, still exactly three steps of 0.1
    assert ParameterRange(0, 1, 0.1).contains(0.1 + 0.2)
    assert not ParameterRange(0, 1, 0.1).contains(0.35)


@given(st.integers(min_value=-1000, max_value=1000))
def test_accepted_onboard_loads_always_lie_in_the_table_range(load):
    """Property: the parser never accepts a load outside PARAMETER_RANGES."""
    bounds = PARAMETER_RANGES["onboard_load"]
    try:
        parsed = parse_scenario_parameters({"onboard_load": load})
    except ScenarioParametersError:
        assert not bounds.contains(load)
    else:
        assert bounds.minimum <= parsed.onboard_load <= bounds.maximum
        assert parsed.onboard_load % 10 == 0
