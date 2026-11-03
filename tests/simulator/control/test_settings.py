# AI contribution: 50% or more AI-generated
"""Tests for control settings parsing (US-2.3 #45, US-2.2 #43)."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from simulator.control.break_even import BreakEvenWeights
from simulator.control.hold_search import HoldSearchSettings
from simulator.control.interface import DecisionController, HoldAction
from simulator.control.registry import StrategyRegistry
from simulator.control.settings import (
    ControlSettings,
    ControlSettingsError,
    OperatingRulesConfig,
    OperatingRulesError,
    parse_control_settings,
    parse_operating_rules,
)
from simulator.control.strategies.no_control import NoControlStrategy
from simulator.scenario import Scenario


class FakeHoldStrategy(DecisionController):
    """Test-only second strategy, so selection is not just the default."""

    name = "fake_hold"

    def evaluate(self, observation):
        return (HoldAction(observation.train_id, 30.0, "fake"),)


REGISTRY = StrategyRegistry((NoControlStrategy, FakeHoldStrategy))


def test_selects_a_registered_non_default_strategy():
    settings = parse_control_settings({"strategy": "fake_hold"}, REGISTRY)
    assert settings == ControlSettings(strategy="fake_hold")


@pytest.mark.parametrize("value", [None, {}])
def test_missing_strategy_defaults_to_no_control(value):
    assert parse_control_settings(value).strategy == "no_control"


def test_settings_save_as_plain_dict_with_search_defaults():
    assert ControlSettings("fake_hold").to_dict() == {
        "strategy": "fake_hold",
        "hold_search": {"step_s": 5.0, "max_hold_s": 60.0},
        "weights": {"w_wait": 2.0, "w_onboard": 1.0},
    }


def test_hold_search_and_weights_are_read_from_the_scenario():
    value = {
        "hold_search": {"step_s": 10, "max_hold_s": 90},
        "weights": {"w_wait": 1.5},
    }
    settings = parse_control_settings(value)
    assert settings.hold_search == HoldSearchSettings(step_s=10.0, max_hold_s=90.0)
    assert settings.weights == BreakEvenWeights(w_wait=1.5, w_onboard=1.0)


def test_saved_settings_load_back_unchanged():
    original = parse_control_settings({"hold_search": {"step_s": 2.5}})
    saved = original.to_dict()
    assert parse_control_settings(saved) == original


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"hold_search": {"step_s": 0}}, r"control\.hold_search: .*step_s"),
        ({"hold_search": {"max_hold_s": 62}}, r"control\.hold_search: .*whole"),
        ({"hold_search": {"step": 5}}, r"control\.hold_search\.step: unknown field"),
        ({"hold_search": [5, 60]}, r"control\.hold_search: must be an object"),
        ({"weights": {"w_wait": -1}}, r"control\.weights: .*w_wait"),
        ({"weights": {"w_onboard": "1"}}, r"control\.weights: .*w_onboard"),
    ],
)
def test_bad_search_settings_name_the_field(value, message):
    with pytest.raises(ControlSettingsError, match=message):
        parse_control_settings(value)


def test_unknown_strategy_lists_registry_choices():
    value = {"strategy": "headway"}
    with pytest.raises(ControlSettingsError, match="choose fake_hold, no_control"):
        parse_control_settings(value, REGISTRY)


@pytest.mark.parametrize("value", [["no_control"], "no_control", 3])
def test_control_must_be_an_object(value):
    with pytest.raises(ControlSettingsError, match="control: must be an object"):
        parse_control_settings(value)


def test_operating_rules_defaults():
    config = OperatingRulesConfig()
    assert config.max_hold_time == 300.0
    assert config.min_safe_gap == 60.0
    assert config.rule_action_map["max_hold_exceeded"] == "CLAMP"
    assert config.rule_action_map["headway_violation"] == "REFUSE"


def test_operating_rules_custom_overrides():
    config = OperatingRulesConfig(max_hold_time=150.0, min_safe_gap=30.0)
    assert config.max_hold_time == 150.0
    assert config.min_safe_gap == 30.0


def test_scenario_manifest_includes_rules():
    config = OperatingRulesConfig(max_hold_time=120.0)
    # Construct a minimal valid Scenario to verify to_dict serialization
    scenario = Scenario(
        dataset_id="test_dataset",
        service_date=date(2026, 10, 19),
        start_time=time(7, 0),
        duration_s=3600,
        repetitions=1,
        master_seed=42,
        interchanges=("mcgill",),
        timezone="America/Toronto",
        dst_fold=None,
        resolved_start=datetime(2026, 10, 19, 7, 0, tzinfo=ZoneInfo("America/Toronto")),
        operating_rules=config,
    )
    manifest = scenario.to_dict()

    assert "operating_rules" in manifest
    assert manifest["operating_rules"]["max_hold_time"] == 120.0
    assert (
        manifest["operating_rules"]["rule_action_map"]["max_hold_exceeded"] == "CLAMP"
    )


def test_operating_rules_partial_rule_action_map_merge():
    # Providing one rule action should merge with the defaults.
    config = parse_operating_rules({"rule_action_map": {"max_hold_exceeded": "REFUSE"}})
    assert config.rule_action_map["max_hold_exceeded"] == "REFUSE"
    assert (
        config.rule_action_map["headway_violation"] == "REFUSE"
    )  # Preserved from default
    assert (
        config.rule_action_map["one_hop_violation"] == "REFUSE"
    )  # Preserved from default


def test_operating_rules_unknown_rule_key_raises_error():
    with pytest.raises(
        OperatingRulesError,
        match="operating_rules.rule_action_map.max_hold_exceded: unknown rule",
    ):
        parse_operating_rules({"rule_action_map": {"max_hold_exceded": "REFUSE"}})
