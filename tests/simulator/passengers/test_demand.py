# AI contribution: 50% or more AI-generated


import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.passengers.demand import DemandPeriod, DemandProfile


@pytest.fixture
def profile():
    return DemandProfile((DemandPeriod(0, 60, 12), DemandPeriod(60, 120, 30)))


def test_expected_count_integrates_each_demand_band(profile):
    # One minute at 12 passengers/minute, then one minute at 30: 12 + 30 = 42.
    assert profile.expected_count(0, 120) == 42
    assert profile.expected_count(0, 60) == 12
    assert profile.expected_count(60, 120) == 30


def test_window_crossing_a_boundary_uses_both_rates(profile):
    # Half a minute at each rate: 12 * 0.5 + 30 * 0.5 = 21.
    assert profile.expected_count(30, 90) == 21


def test_gaps_and_time_outside_the_profile_have_zero_demand():
    profile = DemandProfile((DemandPeriod(10, 20, 60), DemandPeriod(40, 70, 120)))

    # Ten seconds at 1 passenger/s, plus 30 seconds at 2 passengers/s = 70.
    assert profile.expected_count(0, 100) == 70
    assert profile.expected_count(20, 40) == 0
    assert profile.expected_count(70, 100) == 0


def test_zero_length_windows_and_empty_profiles_have_zero_demand(profile):
    assert profile.expected_count(60, 60) == 0
    assert DemandProfile().expected_count(0, 600) == 0
    assert DemandProfile((DemandPeriod(0, 60, 0),)).expected_count(0, 60) == 0


def test_profile_copies_a_mutable_period_sequence():
    periods = [DemandPeriod(0, 60, 12)]
    profile = DemandProfile(periods)
    periods.append(DemandPeriod(60, 120, 30))

    assert profile.periods == (DemandPeriod(0, 60, 12),)
    assert profile.expected_count(0, 120) == 12


@pytest.mark.parametrize(
    "name,invalid",
    [
        ("start_s", -1),
        ("end_s", math.inf),
        ("passengers_per_minute", -1),
        ("passengers_per_minute", math.nan),
        ("passengers_per_minute", True),
        ("passengers_per_minute", "10"),
    ],
)
def test_invalid_period_values_are_rejected_naming_the_field(name, invalid):
    values = {"start_s": 0, "end_s": 60, "passengers_per_minute": 12, name: invalid}

    with pytest.raises(ValueError, match=name):
        DemandPeriod(**values)


@pytest.mark.parametrize("start_s,end_s", [(0, 0), (10, 5)])
def test_period_must_have_positive_duration(start_s, end_s):
    with pytest.raises(ValueError, match="end_s"):
        DemandPeriod(start_s, end_s, 12)


@pytest.mark.parametrize(
    "periods",
    [
        (DemandPeriod(0, 70, 12), DemandPeriod(60, 120, 30)),
        (DemandPeriod(60, 120, 30), DemandPeriod(0, 60, 12)),
    ],
)
def test_overlapping_or_unordered_periods_are_rejected(periods):
    with pytest.raises(ValueError, match="periods"):
        DemandProfile(periods)


@pytest.mark.parametrize("invalid", [None, "", [42]])
def test_profile_requires_a_sequence_of_demand_periods(invalid):
    with pytest.raises(ValueError, match="periods"):
        DemandProfile(invalid)


@pytest.mark.parametrize(
    "name,invalid", [("start_s", -1), ("end_s", math.nan), ("end_s", True)]
)
def test_invalid_window_values_are_rejected(profile, name, invalid):
    window = {"start_s": 0, "end_s": 60, name: invalid}

    with pytest.raises(ValueError, match=name):
        profile.expected_count(**window)


def test_window_cannot_end_before_it_starts(profile):
    with pytest.raises(ValueError, match="end_s"):
        profile.expected_count(90, 60)


def test_unrepresentable_numbers_and_expected_counts_are_rejected():
    with pytest.raises(ValueError, match="passengers_per_minute"):
        DemandPeriod(0, 60, 10**400)
    with pytest.raises(ValueError, match="expected passenger count"):
        DemandProfile((DemandPeriod(0, 1e308, 1e308),)).expected_count(0, 1e308)


@given(split_s=st.floats(min_value=0, max_value=120, allow_nan=False))
def test_splitting_a_window_preserves_expected_volume(split_s):
    profile = DemandProfile((DemandPeriod(0, 60, 12), DemandPeriod(60, 120, 30)))
    split_volume = profile.expected_count(0, split_s) + profile.expected_count(
        split_s, 120
    )

    # Only rounding in two integrations is tolerated; total demand is exactly 42.
    assert split_volume == pytest.approx(42, rel=0, abs=1e-12)
