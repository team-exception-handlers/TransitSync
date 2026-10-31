# AI contribution: 50% or more AI-generated
"""Tests for strategy registration and selection by name (US-2.3, #49)."""

import pytest

from simulator.control.interface import DecisionController, HoldAction
from simulator.control.registry import StrategyRegistry, UnknownStrategyError
from simulator.control.strategies import STRATEGIES
from simulator.control.strategies.no_control import NoControlStrategy


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
