# AI contribution: 50% or more AI-generated
"""Hand-calculated dwell examples and configuration boundaries."""

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.trains.dwell import DwellModel


@pytest.mark.parametrize(
    ("boarded", "alighted", "expected_s"),
    [(0, 0, 20.0), (10, 0, 35.0), (0, 8, 26.0), (10, 8, 41.0)],
)
def test_hand_calculated_dwell(boarded, alighted, expected_s):
    # Illustrative coefficients, not calibrated Metro/REM measurements.
    # Mixed example: 20 + 1.5 * 10 + 0.75 * 8 = 41 seconds.
    model = DwellModel(20.0, 1.5, 0.75)
    assert model.compute(boarded_count=boarded, alighted_count=alighted) == expected_s


def test_numpy_counts_are_accepted():
    counts = np.array([10, 8], dtype=np.int64)
    model = DwellModel(20.0, 1.5, 0.75)
    assert model.compute(boarded_count=counts[0], alighted_count=counts[1]) == 41.0


def test_each_passenger_flow_increases_dwell():
    model = DwellModel(20.0, 1.5, 0.75)
    baseline = model.compute(boarded_count=10, alighted_count=8)
    assert model.compute(boarded_count=11, alighted_count=8) > baseline
    assert model.compute(boarded_count=10, alighted_count=9) > baseline


def test_zero_coefficients_disable_passenger_terms():
    model = DwellModel(20, 0, 0)
    assert model.compute(boarded_count=100, alighted_count=80) == 20.0
    assert DwellModel(0, 0, 0).compute(boarded_count=0, alighted_count=0) == 0.0


@pytest.mark.parametrize(
    "field",
    [
        "base_dwell_s",
        "boarding_s_per_passenger",
        "alighting_s_per_passenger",
        "crowding_strength",
    ],
)
@pytest.mark.parametrize(
    "value", [-1, float("nan"), float("inf"), True, "2", None, 10**400]
)
def test_invalid_coefficient_names_the_field(field, value):
    config = dict(
        base_dwell_s=20.0,
        boarding_s_per_passenger=1.5,
        alighting_s_per_passenger=0.75,
    )
    config[field] = value
    with pytest.raises(ValueError, match=field):
        DwellModel(**config)


@pytest.mark.parametrize("field", ["boarded_count", "alighted_count"])
@pytest.mark.parametrize("value", [-1, 1.5, True, "2", None, float("inf")])
def test_invalid_passenger_count_names_the_field(field, value):
    counts = dict(boarded_count=0, alighted_count=0)
    counts[field] = value
    with pytest.raises(ValueError, match=field):
        DwellModel(20.0, 1.5, 0.75).compute(**counts)


@pytest.mark.parametrize("count", [2, 10**400])
def test_overflow_is_rejected(count):
    with pytest.raises(ValueError, match="finite"):
        DwellModel(20.0, 1e308, 0.75).compute(boarded_count=count, alighted_count=0)


@pytest.mark.parametrize(("load", "expected_s"), [(0, 41.0), (50, 43.625), (100, 83.0)])
def test_hand_calculated_crowding(load, expected_s):
    # service = 21; penalty = 21 * 2 * (load / 100)**4.
    model = DwellModel(20, 1.5, 0.75, crowding_strength=2)
    assert (
        model.compute(
            boarded_count=10, alighted_count=8, onboard_load=load, capacity=100
        )
        == expected_s
    )


def test_equal_load_steps_increase_dwell_more_sharply_near_capacity():
    model = DwellModel(20, 1.5, 0.75, crowding_strength=2)
    times = {
        load: model.compute(
            boarded_count=10, alighted_count=8, onboard_load=load, capacity=100
        )
        for load in (10, 20, 80, 90, 100)
    }
    assert times[100] - times[90] > times[90] - times[80]
    assert times[90] - times[80] > times[20] - times[10] > 0


def test_crowding_depends_on_load_fraction_and_accepts_numpy_counts():
    model = DwellModel(20, 1.5, 0.75, crowding_strength=2)
    assert model.compute(
        boarded_count=10, alighted_count=8, onboard_load=np.int64(50), capacity=100
    ) == model.compute(
        boarded_count=10, alighted_count=8, onboard_load=500, capacity=np.int64(1000)
    )


def test_disabled_crowding_preserves_existing_dwell_at_full_capacity():
    assert (
        DwellModel(20, 1.5, 0.75).compute(
            boarded_count=10, alighted_count=8, onboard_load=100, capacity=100
        )
        == 41.0
    )


@pytest.mark.parametrize(("boarded", "alighted"), [(0, 0), (10, 0), (0, 8)])
def test_crowding_scales_only_passenger_service(boarded, alighted):
    model = DwellModel(20, 1.5, 0.75, crowding_strength=2)
    assert model.compute(
        boarded_count=boarded, alighted_count=alighted, onboard_load=100, capacity=100
    ) == 20 + 3 * (1.5 * boarded + 0.75 * alighted)


@pytest.mark.parametrize("strength", [0, 2])
@pytest.mark.parametrize(
    ("load", "capacity", "field"),
    [
        (None, 100, "onboard_load"),
        (10, None, "capacity"),
        (-1, 100, "onboard_load"),
        (101, 100, "onboard_load"),
        (True, 100, "onboard_load"),
        (1.5, 100, "onboard_load"),
        ("10", 100, "onboard_load"),
        (float("nan"), 100, "onboard_load"),
        (0, 0, "capacity"),
        (0, -1, "capacity"),
        (0, True, "capacity"),
        (0, 1.5, "capacity"),
        (0, "100", "capacity"),
        (0, float("inf"), "capacity"),
    ],
)
def test_invalid_load_and_capacity(strength, load, capacity, field):
    with pytest.raises(ValueError, match=field):
        DwellModel(20, 1.5, 0.75, strength).compute(
            boarded_count=0, alighted_count=0, onboard_load=load, capacity=capacity
        )


def test_enabled_crowding_requires_load_and_capacity():
    with pytest.raises(ValueError, match="onboard_load"):
        DwellModel(20, 1.5, 0.75, 2).compute(boarded_count=0, alighted_count=0)


def test_crowding_overflow_is_rejected():
    with pytest.raises(ValueError, match="finite"):
        DwellModel(20, 1.5, 0.75, 1e308).compute(
            boarded_count=10, alighted_count=0, onboard_load=100, capacity=100
        )


@pytest.mark.parametrize("count_type", [np.int64, np.uint64])
@pytest.mark.parametrize("flow", ["boarded_count", "alighted_count"])
def test_large_numpy_counts_match_python_integers(count_type, flow):
    model = DwellModel(20, 2, 2, crowding_strength=2)
    counts = dict(boarded_count=0, alighted_count=0)
    counts[flow] = 2**62
    expected = model.compute(**counts, onboard_load=100, capacity=100)
    counts[flow] = count_type(2**62)
    # NumPy scalar multiplication would wrap before conversion to float.
    with np.errstate(over="raise"):
        actual = model.compute(**counts, onboard_load=100, capacity=100)
    assert actual == expected == float(6 * 2**62 + 20)


def test_large_mixed_integer_load_above_capacity_is_rejected():
    with pytest.raises(ValueError, match="onboard_load"):
        DwellModel(20, 1.5, 0.75, 2).compute(
            boarded_count=0,
            alighted_count=0,
            onboard_load=np.uint64(2**63),
            capacity=np.int64(2**63 - 1),
        )


def test_zero_service_keeps_base_even_with_extreme_crowding_strength():
    assert (
        DwellModel(20, 0, 0, 1e308).compute(
            boarded_count=10, alighted_count=8, onboard_load=100, capacity=100
        )
        == 20.0
    )


@given(
    capacity=st.integers(min_value=1, max_value=10000),
    first=st.integers(min_value=0, max_value=10000),
    second=st.integers(min_value=0, max_value=10000),
    boarded=st.integers(min_value=0, max_value=1000),
    alighted=st.integers(min_value=0, max_value=1000),
    strength=st.floats(min_value=0, max_value=10),
)
def test_crowding_is_monotone_and_bounded(
    capacity, first, second, boarded, alighted, strength
):
    low, high = sorted((min(first, capacity), min(second, capacity)))
    model = DwellModel(20, 1.5, 0.75, strength)
    times = [
        model.compute(
            boarded_count=boarded,
            alighted_count=alighted,
            onboard_load=load,
            capacity=capacity,
        )
        for load in (0, low, high, capacity)
    ]
    assert times == sorted(times)
    assert times[0] == 20 + 1.5 * boarded + 0.75 * alighted
    assert times[-1] == pytest.approx(
        20 + (1.5 * boarded + 0.75 * alighted) * (1 + strength)
    )
