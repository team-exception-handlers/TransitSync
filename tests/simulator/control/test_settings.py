# AI contribution: 50% or more AI-generated
"""Tests for control settings parsing (US-2.3, Task 2.3.1, #45)."""

import pytest

from simulator.control.interface import DecisionController, HoldAction
from simulator.control.registry import StrategyRegistry
from simulator.control.settings import (
    ControlSettings,
    ControlSettingsError,
    parse_control_settings,
)
from simulator.control.strategies.no_control import NoControlStrategy


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
