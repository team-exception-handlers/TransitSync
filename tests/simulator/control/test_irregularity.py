# AI contribution: 50% or more AI-generated
"""Hand-calculated departure irregularity and settings checks for Issue #63."""

import pytest

from simulator.control.irregularity import ServiceIrregularity
from simulator.control.settings import ControlSettingsError, parse_control_settings
from simulator.engine.events import TrainDeparture


def departure(actual_s, scheduled_s, platform_id="east"):
    """Create a completed departure with no passengers or holding."""
    return TrainDeparture(
        time_s=actual_s,
        train_id=f"train-{actual_s}",
        station_id="station",
        platform_id=platform_id,
        scheduled_s=scheduled_s,
        disruption_delay_s=0,
        hold_s=0,
        boarded_count=0,
        alighted_count=0,
        onboard_load=0,
    )


def readings(times, window_size=5):
    """Record a sequence against a fixed 60-second platform target."""
    detector = ServiceIrregularity(window_size, {"east": 60})
    values = []
    for actual_s in times:
        detector.record_departure(departure(actual_s, 0), "green")
        values.append(detector.value("green", "east"))
    return values


def test_regular_headways_have_zero_deviation():
    assert readings([0, 60, 120, 180]) == [None, 0.0, 0.0, 0.0]


def test_short_and_long_headways_both_count():
    # Gaps of 60, 75 and 45 s yield deviations of 0, 1/4 and 1/4.
    assert readings([0, 60, 135, 180])[-1] == pytest.approx(1 / 6)


def test_increasing_deviation_is_unbounded_and_repeatable():
    # Gaps of 60, 120 and 240 s yield deviations of 0, 1 and 3.
    times = [0, 60, 180, 420]
    first = readings(times)
    second = readings(times)
    assert first == [None, 0.0, 0.5, 4 / 3]
    assert second == first


def test_recent_regular_gaps_displace_irregular_gaps():
    # Two 120-second gaps enter the window, then two 60-second gaps evict them.
    assert readings([0, 120, 240, 300, 360], 2) == [None, 1.0, 1.0, 0.5, 0.0]


def test_no_value_until_a_valid_timetable_gap_exists():
    detector = ServiceIrregularity(3)
    assert detector.value("green", "east") is None
    detector.record_departure(departure(10, 10), "green")
    assert detector.value("green", "east") is None
    detector.record_departure(departure(70, 10), "green")
    assert detector.value("green", "east") is None
    detector.record_departure(departure(140, 70), "green")
    # A 70-second actual gap against the next valid 60-second timetable gap.
    assert detector.value("green", "east") == pytest.approx(1 / 6)


def test_lines_and_directional_platforms_have_separate_history():
    detector = ServiceIrregularity(3, {"east": 60, "west": 60})
    detector.record_departure(departure(0, 0), "green")
    detector.record_departure(departure(20, 0), "blue")
    detector.record_departure(departure(40, 0, "west"), "green")
    assert detector.value("green", "east") is None
    assert detector.value("blue", "east") is None
    assert detector.value("green", "west") is None
    detector.record_departure(departure(60, 0), "green")
    detector.record_departure(departure(110, 0), "blue")
    assert detector.value("green", "east") == 0.0
    assert detector.value("blue", "east") == 0.5
    assert detector.value("green", "west") is None


@pytest.mark.parametrize("window", [0, -1, 2.0, "3", True, None, 10**100])
def test_invalid_window_names_the_control_field(window):
    config = {"irregularity_window_size": window}
    with pytest.raises(
        ControlSettingsError, match=r"control\.irregularity_window_size"
    ):
        parse_control_settings(config)


@pytest.mark.parametrize("target", [0, -60, float("inf"), float("nan")])
def test_configured_targets_use_existing_headway_validation(target):
    config = {
        "strategy": "headway_regulation",
        "target_headways_s": {"east": target},
        "irregularity_window_size": 3,
    }
    with pytest.raises(ControlSettingsError, match=r"control\.target_headways_s.*east"):
        parse_control_settings(config)


def test_window_setting_defaults_and_round_trips():
    assert parse_control_settings(None).irregularity_window_size == 5
    configured = parse_control_settings({"irregularity_window_size": 3})
    assert configured.to_dict()["irregularity_window_size"] == 3
    assert parse_control_settings(configured.to_dict()) == configured
