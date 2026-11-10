# AI contribution: 50% or more AI-generated
"""US-2.6 #61: validate forward-window and exact-search limits."""

import pytest

from simulator.control.planning import RollingHorizonSettings


@pytest.mark.parametrize("value", [0, -1, True, float("nan"), float("inf"), "300"])
def test_window_requires_positive_finite_seconds(value):
    with pytest.raises(ValueError, match="window_s"):
        RollingHorizonSettings(window_s=value)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "10"])
def test_combination_budget_requires_positive_integer(value):
    with pytest.raises(ValueError, match="max_combinations"):
        RollingHorizonSettings(max_combinations=value)
