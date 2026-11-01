# AI contribution: 50% or more AI-generated
"""Tests for control settings parsing (US-2.3 #45, US-2.2 #43)."""

import pytest

from simulator.control.break_even import BreakEvenWeights
from simulator.control.hold_search import HoldSearchSettings
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
