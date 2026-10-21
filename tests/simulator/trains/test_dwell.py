# AI contribution: 50% or more AI-generated
"""Hand-calculated dwell examples and configuration boundaries."""

import pytest

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
    ["base_dwell_s", "boarding_s_per_passenger", "alighting_s_per_passenger"],
)
@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "2", None])
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
