# AI contribution: 50% or more AI-generated
"""Tests for the break-even function (US-2.2, Task 2.2.2, #42).

Every expected value is worked out by hand from Mathematical Foundations
section 1: Benefit = N * H * w_wait, Cost = L * h * w_onboard + downstream.
"""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.control.break_even import (
    BreakEvenResult,
    BreakEvenWeights,
    evaluate_hold,
)

EQUAL = BreakEvenWeights(w_wait=1.0, w_onboard=1.0)

counts = st.floats(min_value=0.0, max_value=2000.0)
seconds = st.floats(min_value=0.0, max_value=900.0)


def test_wiki_example_holds_by_a_small_margin():
    # 20 caught * 300 s headway = 6,000; 180 on board * 30 s = 5,400
    result = evaluate_hold(30.0, 20.0, 300.0, 180, EQUAL)
    assert result == BreakEvenResult(30.0, 20.0, 6000.0, 5400.0)
    assert result.net_ps == 600.0
    assert result.worthwhile


def test_full_train_makes_the_same_hold_not_worthwhile():
    # 20 * 300 = 6,000 against 400 * 30 = 12,000
    result = evaluate_hold(30.0, 20.0, 300.0, 400, EQUAL)
    assert result.net_ps == -6000.0
    assert not result.worthwhile


def test_weights_scale_each_side():
    # Benefit 20 * 300 * 2.0 = 12,000; cost 400 * 30 * 1.5 = 18,000
    weights = BreakEvenWeights(w_wait=2.0, w_onboard=1.5)
    result = evaluate_hold(30.0, 20.0, 300.0, 400, weights)
    assert (result.benefit_ps, result.cost_ps) == (12000.0, 18000.0)


def test_default_weights_count_waiting_twice():
    # Benefit 20 * 300 * 2 = 12,000 now beats the 5,400 cost by more
    result = evaluate_hold(30.0, 20.0, 300.0, 180, BreakEvenWeights())
    assert result.net_ps == 6600.0


def test_downstream_cost_is_added_to_the_onboard_cost():
    # 180 * 30 + 1,000 = 6,400, which now beats the 6,000 benefit
    result = evaluate_hold(30.0, 20.0, 300.0, 180, EQUAL, downstream_cost_ps=1000.0)
    assert result.cost_ps == 6400.0
    assert not result.worthwhile


def test_benefit_exactly_equal_to_cost_declines():
    # 18 * 300 = 5,400 = 180 * 30: nothing gained, so do not hold
    result = evaluate_hold(30.0, 18.0, 300.0, 180, EQUAL)
    assert result.net_ps == 0.0
    assert not result.worthwhile


def test_zero_hold_has_no_onboard_cost():
    result = evaluate_hold(0.0, 0.0, 300.0, 500, EQUAL)
    assert (result.benefit_ps, result.cost_ps) == (0.0, 0.0)


@given(
    hold=seconds,
    caught=counts,
    headway=seconds,
    load=counts,
    w_wait=st.floats(min_value=0.0, max_value=5.0),
)
def test_holds_exactly_when_time_saved_beats_time_lost(
    hold, caught, headway, load, w_wait
):
    weights = BreakEvenWeights(w_wait=w_wait, w_onboard=1.0)
    result = evaluate_hold(hold, caught, headway, load, weights)
    assert result.worthwhile == (caught * headway * w_wait > load * hold)


@given(hold=seconds, caught=counts, headway=seconds, load=counts)
def test_same_inputs_give_the_same_output_and_change_nothing(
    hold, caught, headway, load
):
    weights = BreakEvenWeights(w_wait=2.0, w_onboard=1.0)
    first = evaluate_hold(hold, caught, headway, load, weights)
    second = evaluate_hold(hold, caught, headway, load, weights)
    assert first == second
    assert weights == BreakEvenWeights(w_wait=2.0, w_onboard=1.0)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("hold_s", -1.0),
        ("n_caught", -0.5),
        ("headway_s", math.nan),
        ("load", math.inf),
        ("downstream_cost_ps", -10.0),
        ("load", "180"),
    ],
)
def test_rejects_bad_input_naming_the_field(field_name, value):
    values = {
        "hold_s": 30.0,
        "n_caught": 20.0,
        "headway_s": 300.0,
        "load": 180,
        "weights": EQUAL,
        "downstream_cost_ps": 0.0,
    } | {field_name: value}
    with pytest.raises(ValueError, match=field_name):
        evaluate_hold(**values)


@pytest.mark.parametrize(
    ("w_wait", "w_onboard", "field_name"),
    [(-1.0, 1.0, "w_wait"), (2.0, math.nan, "w_onboard"), (False, 1.0, "w_wait")],
)
def test_weights_reject_bad_values(w_wait, w_onboard, field_name):
    with pytest.raises(ValueError, match=field_name):
        BreakEvenWeights(w_wait=w_wait, w_onboard=w_onboard)
