# AI contribution: 50% or more AI-generated
"""Check adaptive settings, delegation, and service scope (#64)."""

import pytest

from simulator.control.interface import ObservationSnapshot, PlatformState, TrainState
from simulator.control.settings import (
    ControlSettings,
    ControlSettingsError,
    parse_control_settings,
)
from simulator.control.strategies import STRATEGIES
from simulator.control.walking_cdf import ShiftedExponentialCdf


def adaptive_settings():
    """Return a valid one-platform adaptive configuration."""
    return {
        "strategy": "adaptive",
        "irregularity_threshold": 0.25,
        "target_headways_s": {"P": 60},
        "connection_headways_s": {"P": 60},
    }


@pytest.mark.parametrize(
    "threshold", [None, -0.1, True, "0.25", float("inf"), float("nan"), 10**400]
)
def test_adaptive_rejects_invalid_thresholds(threshold):
    config = {**adaptive_settings(), "irregularity_threshold": threshold}
    with pytest.raises(ControlSettingsError, match=r"control\.irregularity_threshold"):
        parse_control_settings(config)


@pytest.mark.parametrize(
    "field", ["irregularity_threshold", "target_headways_s", "connection_headways_s"]
)
def test_adaptive_requires_threshold_and_both_headway_maps(field):
    config = adaptive_settings()
    del config[field]
    with pytest.raises(ControlSettingsError, match=rf"control\.{field}: required"):
        parse_control_settings(config)


def test_direct_settings_reject_threshold_for_other_strategies():
    with pytest.raises(ControlSettingsError, match="only valid for adaptive"):
        ControlSettings(irregularity_threshold=0.25)


def test_adaptive_settings_round_trip():
    control = parse_control_settings(adaptive_settings())
    saved = control.to_dict()
    assert saved["irregularity_threshold"] == 0.25
    assert parse_control_settings(saved) == control


def observation(time_s, platform_id, score, *, line_id="green"):
    """Give headway regulation a 40-second gap against a 60-second target."""
    return ObservationSnapshot(
        time_s=time_s,
        train_id="T",
        station_id="S",
        platform_id=platform_id,
        scheduled_departure_s=time_s,
        trains=(TrainState("T", line_id, None, None, None, 0, 0, 800),),
        platforms=(PlatformState(platform_id, 0, time_s - 40),),
        incoming_transfers=(),
        service_irregularity=score,
    )


def test_adaptive_switches_only_for_the_deciding_service():
    strategy = STRATEGIES.build(
        "adaptive",
        target_headways_s={"P": 60, "Q": 60},
        connection_headways_s={"P": 60},
        walking_by_platform={"P": ShiftedExponentialCdf(120, 30)},
        irregularity_threshold=0.25,
    )
    decisions = [
        observation(100, "P", None),
        observation(110, "P", 0.5),
        observation(120, "Q", 0.1),
        observation(130, "P", 0.1, line_id="blue"),
        observation(140, "P", None),
        observation(150, "P", 0.5),
        observation(160, "P", 0.25),
    ]
    # A 20-second request proves headway regulation was selected immediately.
    holds = [
        sum(action.duration_s for action in strategy.evaluate(snapshot))
        for snapshot in decisions
    ]
    assert holds == [0, 20, 0, 0, 20, 20, 0]

    switches = [
        record
        for record in strategy.decision_records()
        if record.get("record_type") == "mode_switch"
    ]
    assert [(record["time_s"], record["to_mode"]) for record in switches] == [
        (110, "headway_regulation"),
        (160, "connection_protection"),
    ]
