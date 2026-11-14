# AI contribution: 50% or more AI-generated
"""Tests for strategy registration and selection by name (US-2.3, #49)."""

import re

import pytest

from simulator.control.interface import DecisionController, HoldAction
from simulator.control.registry import StrategyRegistry, UnknownStrategyError
from simulator.control.strategies import STRATEGIES
from simulator.control.strategies.no_control import NoControlStrategy
from simulator.control.strategies.schedule_based_holding import (
    ScheduleBasedHoldingStrategy,
)
from simulator.control.walking_cdf import ShiftedExponentialCdf


class FakeHoldStrategy(DecisionController):
    """Test-only strategy that always asks for a 30 s hold."""

    name = "fake_hold"

    def evaluate(self, observation):
        return (HoldAction(observation.train_id, 30.0, "fake"),)


class SameNameStrategy(FakeHoldStrategy):
    """Reuses ``fake_hold``, which a registry must refuse."""


class AbstractStrategy(DecisionController):
    name = "abstract"


class NamelessStrategy(DecisionController):
    def evaluate(self, observation):
        return ()


def test_name_resolves_to_its_class():
    registry = StrategyRegistry((NoControlStrategy, FakeHoldStrategy))
    strategy = registry.build("fake_hold")
    assert type(strategy) is FakeHoldStrategy


def test_each_build_returns_a_new_instance():
    registry = StrategyRegistry((FakeHoldStrategy,))
    first = registry.build("fake_hold")
    second = registry.build("fake_hold")
    assert first is not second


def test_names_are_sorted():
    registry = StrategyRegistry((NoControlStrategy, FakeHoldStrategy))
    assert registry.names() == ("fake_hold", "no_control")


def test_built_in_registry_offers_no_control():
    assert "no_control" in STRATEGIES
    assert type(STRATEGIES.build("no_control")) is NoControlStrategy


def test_built_in_registry_offers_schedule_based_holding():
    """Check that selecting 'schedule_based' creates the correct strategy."""
    assert "schedule_based" in STRATEGIES
    assert type(STRATEGIES.build("schedule_based")) is ScheduleBasedHoldingStrategy


@pytest.mark.parametrize("name", ["headway", "NO_CONTROL", "", None, 3])
def test_unknown_name_fails_and_lists_valid_names(name):
    registry = StrategyRegistry((NoControlStrategy, FakeHoldStrategy))
    with pytest.raises(UnknownStrategyError, match="available: fake_hold, no_control"):
        registry.build(name)


def test_duplicate_name_is_rejected():
    classes = (FakeHoldStrategy, SameNameStrategy)
    with pytest.raises(ValueError, match="'fake_hold' is registered twice"):
        StrategyRegistry(classes)


@pytest.mark.parametrize(
    ("strategy_class", "message"),
    [
        (AbstractStrategy, "does not implement evaluate"),
        (NamelessStrategy, "name must be a non-empty string"),
        (object, "is not a DecisionController"),
        ("no_control", "is not a DecisionController"),
    ],
)
def test_invalid_strategy_class_is_rejected(strategy_class, message):
    classes = (strategy_class,)
    with pytest.raises(ValueError, match=message):
        StrategyRegistry(classes)


# One platform's inputs, valid for every strategy that needs them
WALKING = {"P": ShiftedExponentialCdf(120, 30)}
HEADWAYS = {"P": 60.0}
ADAPTIVE = {
    "target_headways_s": HEADWAYS,
    "irregularity_threshold": 0.25,
    "walking_by_platform": WALKING,
    "connection_headways_s": HEADWAYS,
}


@pytest.mark.parametrize(
    ("name", "inputs"),
    [
        ("adaptive", ADAPTIVE),
        (
            "connection_protection",
            {"walking_by_platform": WALKING, "connection_headways_s": HEADWAYS},
        ),
        ("headway_regulation", {"target_headways_s": HEADWAYS}),
        ("rolling_horizon", {"walking_by_platform": WALKING}),
        ("no_control", {}),
        ("schedule_based", {}),
    ],
)
def test_build_returns_the_named_strategy_from_its_inputs(name, inputs):
    assert STRATEGIES.build(name, **inputs).name == name


# Several cases pass two bad inputs to pin which error is reported first.
@pytest.mark.parametrize(
    ("name", "inputs", "message"),
    [
        (
            "adaptive",
            {"target_headways_s": HEADWAYS},
            "target_headways_s and irregularity_threshold required for adaptive",
        ),
        (
            "adaptive",
            {"target_headways_s": HEADWAYS, "irregularity_threshold": 0.25},
            "walking_by_platform and connection_headways_s required for adaptive",
        ),
        (
            "connection_protection",
            {"irregularity_threshold": 0.25, "target_headways_s": HEADWAYS},
            "irregularity_threshold only valid for adaptive",
        ),
        (
            "connection_protection",
            {"target_headways_s": HEADWAYS},
            "target_headways_s only valid for headway_regulation",
        ),
        (
            "connection_protection",
            {"walking_by_platform": WALKING},
            "walking_by_platform and connection_headways_s required for "
            "connection_protection",
        ),
        (
            "headway_regulation",
            {"connection_headways_s": HEADWAYS},
            "connection_headways_s only valid for connection_protection",
        ),
        (
            "headway_regulation",
            {},
            "target_headways_s required for headway_regulation",
        ),
        (
            "rolling_horizon",
            {"target_headways_s": HEADWAYS},
            "target_headways_s only valid for headway_regulation",
        ),
        (
            "rolling_horizon",
            {},
            "walking_by_platform required for rolling_horizon",
        ),
        (
            "no_control",
            {"connection_headways_s": HEADWAYS, "target_headways_s": HEADWAYS},
            "connection_headways_s only valid for connection_protection",
        ),
        (
            "schedule_based",
            {"irregularity_threshold": 0.25, "target_headways_s": HEADWAYS},
            "irregularity_threshold only valid for adaptive",
        ),
    ],
)
def test_build_rejects_missing_or_unused_inputs(name, inputs, message):
    with pytest.raises(ValueError, match=f"^{re.escape(message)}$"):
        STRATEGIES.build(name, **inputs)
