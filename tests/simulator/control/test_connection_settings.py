# AI contribution: 50% or more AI-generated
"""Check saved connection headways and registry construction (#51).

Use one table for invalid headway values. Route coverage and actual holds
are checked separately by the construction and full-run tests.
"""

import pytest

from simulator.control.break_even import BreakEvenWeights
from simulator.control.hold_search import HoldSearchSettings
from simulator.control.settings import (
    ControlSettings,
    ControlSettingsError,
    parse_control_settings,
)
from simulator.control.strategies import STRATEGIES
from simulator.control.strategies.connection_protection import (
    ConnectionProtectionStrategy,
)
from simulator.control.walking_cdf import ShiftedExponentialCdf


@pytest.mark.parametrize(
    "headways",
    [
        None,
        [],
        "green",
        300,
        {"": 300},
        {" ": 300},
        {3: 300},
        {"green": True},
        {"green": False},
        {"green": "300"},
        {"green": None},
        {"green": 0},
        {"green": -1},
        {"green": float("nan")},
        {"green": float("inf")},
        {"green": -float("inf")},
        {"green": 10**400},
    ],
)
def test_connection_headways_reject_invalid_values(headways):
    """Require platform IDs and finite positive service headways in seconds.

    This table owns numeric validation for the saved connection settings.
    Strategy and run tests reuse that validation without repeating these cases.
    """
    value = {"strategy": "connection_protection", "connection_headways_s": headways}
    with pytest.raises(ControlSettingsError, match=r"control\.connection_headways_s"):
        parse_control_settings(value)


def test_connection_headways_are_required():
    """Selecting connection protection must supply its service headways.

    Missing values fail when the scenario loads, before a train can start.
    """
    value = {"strategy": "connection_protection"}
    with pytest.raises(ControlSettingsError, match=r"control\.connection_headways_s"):
        parse_control_settings(value)


@pytest.mark.parametrize(
    "strategy",
    ["no_control", "schedule_based", "headway_regulation", "rolling_horizon"],
)
@pytest.mark.parametrize("headways", [None, {}, {"green": 300}])
def test_other_strategies_reject_connection_fields(strategy, headways):
    """Reject a supplied connection-only field, even when it is null or empty.

    This catches accidental settings left behind when changing strategies.
    """
    value = {"strategy": strategy, "connection_headways_s": headways}
    with pytest.raises(ControlSettingsError, match=r"control\.connection_headways_s"):
        parse_control_settings(value)


def test_connection_settings_copy_and_freeze_headways():
    """Caller changes and serialized output cannot change saved settings.

    Use a fractional headway to check that seconds are not rounded.
    Direct construction uses the same validation as loaded JSON.
    """
    headways = {"green": 300.25}
    control = ControlSettings(
        strategy="connection_protection", connection_headways_s=headways
    )
    headways.clear()
    saved = control.to_dict()
    saved["connection_headways_s"]["green"] = 1
    assert control.to_dict()["connection_headways_s"] == {"green": 300.25}
    with pytest.raises(TypeError):
        control.connection_headways_s["green"] = 1


def test_connection_registry_builds_fresh_strategies():
    """The registry builds searches from walking models and saved settings.

    Each call must create a strategy with its own decision history.
    Route preparation is checked by the construction tests.
    """
    walking = {"green": ShiftedExponentialCdf(120, 30)}
    weights = BreakEvenWeights(w_wait=1.5, w_onboard=0.75)
    settings = HoldSearchSettings(step_s=10, max_hold_s=90)
    first = STRATEGIES.build(
        "connection_protection",
        walking_by_platform=walking,
        connection_headways_s={"green": 300},
        weights=weights,
        hold_search=settings,
    )
    second = STRATEGIES.build(
        "connection_protection",
        walking_by_platform=walking,
        connection_headways_s={"green": 300},
        weights=weights,
        hold_search=settings,
    )
    assert type(first) is ConnectionProtectionStrategy
    assert first is not second
    assert first.searches["green"] is not second.searches["green"]
    assert first.searches["green"].weights == weights
    assert first.searches["green"].settings == settings
    assert first.decision_records() == ()
    assert second.decision_records() == ()


@pytest.mark.parametrize("walking, headways", [(None, None), ({}, None), (None, {})])
def test_connection_registry_requires_both_inputs(walking, headways):
    """A registered strategy still needs both of its required maps.

    Fail at construction instead of creating a strategy that fails on departure.
    """
    with pytest.raises(
        ValueError, match="walking_by_platform and connection_headways_s required"
    ):
        STRATEGIES.build(
            "connection_protection",
            walking_by_platform=walking,
            connection_headways_s=headways,
        )


@pytest.mark.parametrize(
    "strategy",
    ["no_control", "schedule_based", "headway_regulation", "rolling_horizon"],
)
def test_registry_rejects_connection_inputs_for_other_strategies(strategy):
    """Other strategies must not silently ignore connection service headways.

    An empty map is still a supplied input and must be rejected.
    """
    supplied = {"connection_headways_s": {}}
    with pytest.raises(ValueError, match="connection.*only valid"):
        STRATEGIES.build(strategy, **supplied)


def test_connection_registry_rejects_headway_targets():
    """Target-gap settings belong to headway regulation, not connection protection."""
    with pytest.raises(ValueError, match="target_headways_s.*only valid"):
        STRATEGIES.build("connection_protection", target_headways_s={})


def test_direct_settings_reject_connection_fields_for_other_strategies():
    """Direct Python setup must follow the same strategy-specific field rule."""
    with pytest.raises(ControlSettingsError, match="connection_headways_s.*only valid"):
        ControlSettings(connection_headways_s={})
