# AI contribution: 50% or more AI-generated
"""Saved headway targets and strategy construction (US-2.3, #48).

Check missing, invalid and mutable target inputs.
Keep the saved format for no-control and schedule-based settings.
"""

import json
from dataclasses import FrozenInstanceError

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulator.control.registry import UnknownStrategyError
from simulator.control.settings import (
    ControlSettings,
    ControlSettingsError,
    parse_control_settings,
)
from simulator.control.strategies import STRATEGIES
from simulator.control.strategies.headway_regulation import HeadwayRegulationStrategy


def configured(targets: object) -> ControlSettings:
    """Parse supplied targets without adding defaults."""
    return parse_control_settings(
        {"strategy": "headway_regulation", "target_headways_s": targets}
    )


def test_targets_preserve_search_and_weights():
    """Adding targets must preserve search settings and weights."""
    control = parse_control_settings(
        {
            "strategy": "headway_regulation",
            "target_headways_s": {"P1": 300.25, "P2": 420},
            "hold_search": {"step_s": 10, "max_hold_s": 90},
            "weights": {"w_wait": 1.5, "w_onboard": 0.75},
        }
    )
    assert control.to_dict() == {
        "strategy": "headway_regulation",
        "target_headways_s": {"P1": 300.25, "P2": 420},
        "hold_search": {"step_s": 10, "max_hold_s": 90},
        "weights": {"w_wait": 1.5, "w_onboard": 0.75},
        "prediction_error": {
            "arrival_kappa": 1.0,
            "transfer_kappa": 1.0,
            "load_kappa": 1.0,
        },
    }


@pytest.mark.parametrize("targets", [None, [], "P1", 300])
def test_target_mapping_shape_is_checked(targets):
    """Reject null, lists, strings and numbers as target maps.

    Check the map's shape before checking its entries.
    """
    value = {"strategy": "headway_regulation", "target_headways_s": targets}
    with pytest.raises(ControlSettingsError, match=r"control\.target_headways_s"):
        parse_control_settings(value)


def test_headway_requires_supplied_targets():
    """Headway selection requires an explicit target map.

    The error must name the target field, not the valid strategy name.
    """
    value = {"strategy": "headway_regulation"}
    with pytest.raises(ControlSettingsError, match=r"control\.target_headways_s"):
        parse_control_settings(value)


@pytest.mark.parametrize("platform", ["", "  ", 5, None])
def test_target_ids_must_be_nonblank_strings(platform):
    """Reject blank or non-string platform IDs.

    Call the parser directly: JSON would turn numeric keys into strings.
    """
    value = {"strategy": "headway_regulation", "target_headways_s": {platform: 300}}
    with pytest.raises(ControlSettingsError, match=r"control\.target_headways_s.*ID"):
        parse_control_settings(value)


@pytest.mark.parametrize(
    "target",
    [
        True,
        False,
        "300",
        None,
        0,
        -1,
        float("nan"),
        float("inf"),
        -float("inf"),
        10**400,
    ],
    ids=[
        "true",
        "false",
        "string",
        "null",
        "zero",
        "negative",
        "nan",
        "inf",
        "-inf",
        "overflow",
    ],
)
def test_target_values_are_finite_positive_seconds(target):
    """Reject invalid target seconds, including bools and huge integers.

    Check the platform in the error to rule out unrelated parser failures.
    """
    value = {"strategy": "headway_regulation", "target_headways_s": {"P1": target}}
    with pytest.raises(ControlSettingsError, match=r"control\.target_headways_s.*P1"):
        parse_control_settings(value)


@pytest.mark.parametrize("strategy", ["no_control", "schedule_based"])
@pytest.mark.parametrize("targets", [{"P1": 300}, {}, None])
def test_unrelated_strategies_reject_supplied_targets(strategy, targets):
    """Other strategies must reject targets, including empty or null maps."""
    value = {"strategy": strategy, "target_headways_s": targets}
    with pytest.raises(ControlSettingsError, match=r"control\.target_headways_s"):
        parse_control_settings(value)


def test_settings_detach_from_caller_and_serialized_copy():
    """Changing caller input or saved output must not change settings.

    Overwrite values to detect shared dictionaries.
    """
    targets = {"P1": 300}
    control = configured(targets)
    targets["P1"] = 250
    saved = control.to_dict()
    saved["target_headways_s"]["P1"] = 200
    assert control.to_dict()["target_headways_s"] == {"P1": 300}


def test_stored_settings_mapping_cannot_be_mutated():
    """Stored target entries cannot be changed."""
    control = configured({"P1": 300})
    with pytest.raises(TypeError):
        control.target_headways_s["P1"] = 250


def test_settings_targets_cannot_be_replaced():
    """The target map itself cannot be replaced."""
    control = configured({"P1": 300})
    with pytest.raises(FrozenInstanceError):
        control.target_headways_s = {"P1": 250}


@pytest.mark.parametrize("strategy", ["no_control", "schedule_based"])
def test_old_serialization_has_no_headway_only_key(strategy):
    """Other strategies keep their saved format."""
    control = parse_control_settings({"strategy": strategy})
    assert control.to_dict() == {
        "strategy": strategy,
        "hold_search": {"step_s": 5.0, "max_hold_s": 60.0},
        "weights": {"w_wait": 2.0, "w_onboard": 1.0},
        "prediction_error": {
            "arrival_kappa": 1.0,
            "transfer_kappa": 1.0,
            "load_kappa": 1.0,
        },
    }


def test_direct_settings_construction_validates_targets():
    """Direct settings construction must also check targets.

    A component factory can create settings without the JSON loader.
    A false target must still be rejected.
    """
    targets = {"P1": False}
    with pytest.raises(ControlSettingsError, match=r"control\.target_headways_s.*P1"):
        ControlSettings(strategy="headway_regulation", target_headways_s=targets)


@pytest.mark.parametrize("strategy", ["no_control", "schedule_based"])
def test_direct_settings_reject_unrelated_targets(strategy):
    """Other strategies reject empty targets without the parser too."""
    targets = {}
    with pytest.raises(ControlSettingsError, match=r"control\.target_headways_s"):
        ControlSettings(strategy=strategy, target_headways_s=targets)


def test_built_in_registry_constructs_fresh_real_headway_instances():
    """Each build creates the real policy with its own target copy."""
    targets = {"P1": 300}
    first = STRATEGIES.build("headway_regulation", target_headways_s=targets)
    second = STRATEGIES.build("headway_regulation", target_headways_s={"P1": 250})
    targets["P1"] = 200
    assert type(first) is HeadwayRegulationStrategy
    assert type(second) is HeadwayRegulationStrategy
    assert first is not second
    assert first.target_headways_s == {"P1": 300}
    assert second.target_headways_s == {"P1": 250}


@pytest.mark.parametrize("targets", [None, {"P1": False}])
def test_registry_reports_bad_headway_configuration(targets):
    """Bad targets raise ValueError, not a missing-argument TypeError."""
    with pytest.raises(ValueError, match="target_headways_s|Target.*P1"):
        STRATEGIES.build("headway_regulation", target_headways_s=targets)


@pytest.mark.parametrize("strategy", ["no_control", "schedule_based"])
def test_registry_rejects_ignored_targets(strategy):
    """Other strategy constructors reject headway targets."""
    targets = {}
    with pytest.raises(ValueError, match="target_headways_s"):
        STRATEGIES.build(strategy, target_headways_s=targets)


def test_unknown_name_still_lists_available_strategies():
    """An unknown name lists the available strategies."""
    with pytest.raises(UnknownStrategyError, match="available: .*headway_regulation"):
        STRATEGIES.build("headway")


@settings(derandomize=True)
@given(
    st.dictionaries(
        st.sampled_from(["P1", "P2", "P3"]),
        st.integers(min_value=1, max_value=4000).map(lambda quarters: quarters / 4),
        min_size=1,
    )
)
def test_target_settings_round_trip(targets):
    """Quarter seconds save and load exactly, without rounding.

    Check the input values too: matching save/load mistakes could otherwise
    make the round-trip comparison pass.
    """
    original = configured(targets)
    restored = parse_control_settings(original.to_dict())
    assert restored == original
    assert restored.target_headways_s == targets


@pytest.mark.parametrize(
    ("target", "expected"), [(np.int64(300), 300.0), (np.float32(300.25), 300.25)]
)
def test_numpy_targets_save_and_load_as_json(target, expected):
    """Save NumPy targets as JSON numbers without losing their value.

    This exercises the settings path as well as direct strategy construction.
    """
    control = configured({"P1": target})
    saved = json.loads(json.dumps(control.to_dict()))
    assert saved["target_headways_s"] == {"P1": expected}
    assert parse_control_settings(saved) == control


def test_large_integer_targets_keep_their_exact_saved_value():
    """Keep integer targets exact even beyond float's whole-number precision.

    Converting 2**53 + 1 to float would round it down by one second.
    """
    control = configured({"P1": 2**53 + 1})
    assert control.to_dict()["target_headways_s"] == {"P1": 9007199254740993}
