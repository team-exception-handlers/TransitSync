# AI contribution: 50% or more AI-generated
"""Tests for the walking-time CDFs (US-2.2, Task 2.2.1, #41)."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.control.walking_cdf import LognormalCdf, ShiftedExponentialCdf

# Same walk the simulator draws by default: mean 300 s, nobody under 30 s
SHIFTED = ShiftedExponentialCdf(mean_s=300.0, min_s=30.0)
# Median walk exp(mu) = 110 s, the wiki's section 3 example
LOGNORMAL = LognormalCdf(mu=math.log(110.0), sigma=0.5)

times = st.floats(min_value=-100.0, max_value=5000.0, allow_nan=False)


@pytest.mark.parametrize("t_s", [-10.0, 0.0, 29.9, 30.0])
def test_shifted_exponential_is_zero_before_the_fastest_walk(t_s):
    assert SHIFTED.cdf(t_s) == 0.0


def test_shifted_exponential_matches_hand_value():
    # F(60) = 1 - exp(-(60 - 30) / 270) = 1 - exp(-1/9) = 0.105161
    assert SHIFTED.cdf(60.0) == pytest.approx(0.105161, abs=1e-6)


def test_lognormal_is_one_half_at_the_median():
    assert LOGNORMAL.cdf(110.0) == pytest.approx(0.5)


def test_lognormal_one_sigma_above_the_median_matches_hand_value():
    # ln t - mu = sigma, so F = Phi(1) = 0.841345 from the normal table
    assert LOGNORMAL.cdf(110.0 * math.exp(0.5)) == pytest.approx(0.841345, abs=1e-6)


@pytest.mark.parametrize("t_s", [-5.0, 0.0])
def test_lognormal_is_zero_for_no_walking_time(t_s):
    assert LOGNORMAL.cdf(t_s) == 0.0


@pytest.mark.parametrize("walking", [SHIFTED, LOGNORMAL])
@given(first=times, second=times)
def test_cdf_never_decreases_and_stays_between_zero_and_one(walking, first, second):
    low, high = sorted((first, second))
    assert 0.0 <= walking.cdf(low) <= walking.cdf(high) <= 1.0


@pytest.mark.parametrize(
    ("mean_s", "min_s", "message"),
    [
        (300.0, -1.0, "min_s"),
        (30.0, 30.0, "exceed"),
        (math.nan, 30.0, "mean_s"),
        (True, 30.0, "mean_s"),
    ],
)
def test_shifted_exponential_rejects_bad_parameters(mean_s, min_s, message):
    with pytest.raises(ValueError, match=message):
        ShiftedExponentialCdf(mean_s=mean_s, min_s=min_s)


@pytest.mark.parametrize(
    ("mu", "sigma", "message"),
    [(4.7, 0.0, "> 0"), (4.7, -0.5, "> 0"), (math.inf, 0.5, "mu"), ("4.7", 0.5, "mu")],
)
def test_lognormal_rejects_bad_parameters(mu, sigma, message):
    with pytest.raises(ValueError, match=message):
        LognormalCdf(mu=mu, sigma=sigma)
