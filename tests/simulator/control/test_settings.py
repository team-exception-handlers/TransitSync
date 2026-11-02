# AI contribution: 50% or more AI-generated
"""Tests for control settings parsing (US-2.3, Task 2.3.1, #45)."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from simulator.control.interface import DecisionController, HoldAction
from simulator.control.registry import StrategyRegistry
from simulator.control.settings import (
    ControlSettings,
    ControlSettingsError,
    OperatingRulesConfig,
    parse_control_settings,
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


def test_settings_save_as_plain_dict():
    assert ControlSettings("fake_hold").to_dict() == {"strategy": "fake_hold"}


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
