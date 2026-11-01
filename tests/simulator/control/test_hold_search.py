# AI contribution: 50% or more AI-generated
"""Tests for the hold length search (US-2.2, Task 2.2.3, #43).

Most cases use a table CDF so every number is easy to check by hand. Its
values are exact in binary, so the sums below hold without rounding. One
group, M = 80, s = 60, H = 300 and both weights 1:

    h      0      10     20      30
    F    0.25   0.50   0.625  0.6875    F(60 + h)
    N      0     20     30      35       80 * (F(60 + h) - 0.25)
    B      0   6000   9000   10500       N * 300
"""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.control.break_even import BreakEvenWeights
from simulator.control.expected_arrivals import TransferEstimate
from simulator.control.hold_search import (
    MAX_CANDIDATES,
    HoldInputs,
    HoldSearch,
    HoldSearchSettings,
)
from simulator.control.interface import (
    IncomingTransfer,
    ObservationSnapshot,
    TrainState,
)
from simulator.control.walking_cdf import ShiftedExponentialCdf

EQUAL = BreakEvenWeights(w_wait=1.0, w_onboard=1.0)
TEN_TO_THIRTY = HoldSearchSettings(step_s=10.0, max_hold_s=30.0)
GROUP = TransferEstimate("g1", 80, 60.0)


class TableCdf:
    """F known only at s + h for the candidates in the module docstring."""

    values = {60.0: 0.25, 70.0: 0.5, 80.0: 0.625, 90.0: 0.6875}

    def cdf(self, t_s):
        return self.values[t_s]


def inputs(load, transfers=(GROUP,), headway_s=300.0):
    return HoldInputs(0.0, "green_1", "mcgill", "green", load, headway_s, transfers)


def search(settings=TEN_TO_THIRTY, weights=EQUAL, walking=None):
    return HoldSearch(walking or TableCdf(), weights, settings)


def nets(result):
    return [candidate.net_ps for candidate in result.candidates]


def test_selects_the_candidate_with_the_best_net():
    # L = 200: J = 0, 6000 - 2000, 9000 - 4000, 10500 - 6000
    result = search().run(inputs(load=200))
    assert nets(result) == [0.0, 4000.0, 5000.0, 4500.0]
    assert result.hold_s == 20.0


def test_returns_no_hold_when_no_candidate_is_worthwhile():
    # L = 1000: J = 0, -4000, -11000, -19500
    result = search().run(inputs(load=1000))
    assert result.chosen is None
    assert result.hold_s == 0.0


def test_tie_goes_to_the_shorter_hold():
    # L = 300: J(10) = 6000 - 3000 = J(20) = 9000 - 6000 = 3000
    result = search().run(inputs(load=300))
    assert nets(result)[1:3] == [3000.0, 3000.0]
    assert result.hold_s == 10.0


def test_zero_is_always_evaluated_first():
    result = search().run(inputs(load=200))
    assert result.candidates[0].hold_s == 0.0


def test_reason_for_a_hold_shows_both_sides():
    result = search().run(inputs(load=200))
    assert result.reason == (
        "hold 20 s: 30.0 caught, benefit 9000.0 > cost 4000.0 passenger-s"
    )


def test_reason_for_a_decline_shows_the_closest_call():
    result = search().run(inputs(load=1000))
    assert result.reason == (
        "no hold: best was 10 s: 20.0 caught, benefit 6000.0 <= cost 10000.0 "
        "passenger-s"
    )


def test_reason_when_nobody_is_walking_to_the_platform():
    result = search().run(inputs(load=200, transfers=()))
    assert result.reason == "no hold: no transfer group is walking to this platform"


def test_maximum_hold_of_zero_never_holds():
    settings = HoldSearchSettings(step_s=10.0, max_hold_s=0.0)
    result = search(settings=settings).run(inputs(load=0))
    assert result.hold_s == 0.0
    assert result.reason == "no hold: the maximum hold is 0 s"


@pytest.mark.parametrize(
    ("step_s", "max_hold_s", "expected"),
    [
        (5, 20, (0.0, 5.0, 10.0, 15.0, 20.0)),
        (10, 0, (0.0,)),
        # 0.1 is not exact in binary; the last candidate is still exactly 0.3
        (0.1, 0.3, (0.0, 0.1, 0.2, 0.3)),
    ],
)
def test_candidates_run_from_zero_to_the_maximum(step_s, max_hold_s, expected):
    candidates = HoldSearchSettings(step_s, max_hold_s).candidates()
    assert candidates == pytest.approx(expected)
    assert candidates[-1] == max_hold_s


def test_settings_store_seconds_as_floats():
    assert HoldSearchSettings(5, 60).to_dict() == {"step_s": 5.0, "max_hold_s": 60.0}


@pytest.mark.parametrize(
    ("step_s", "max_hold_s", "message"),
    [
        (0, 60, "step_s must be > 0"),
        (-5, 60, "step_s must be > 0"),
        (5, -5, "max_hold_s"),
        (5, 62, "whole number"),
        (math.nan, 60, "step_s"),
        (True, 60, "step_s"),
        (0.5, MAX_CANDIDATES, "more than"),
    ],
)
def test_settings_reject_bad_values(step_s, max_hold_s, message):
    with pytest.raises(ValueError, match=message):
        HoldSearchSettings(step_s, max_hold_s)


@given(
    load=st.integers(min_value=0, max_value=1500),
    size=st.integers(min_value=0, max_value=400),
    window=st.floats(min_value=-120.0, max_value=600.0),
    headway=st.floats(min_value=60.0, max_value=900.0),
)
def test_chosen_hold_is_never_beaten_and_stays_in_range(load, size, window, headway):
    walking = ShiftedExponentialCdf(mean_s=300.0, min_s=30.0)
    transfers = (TransferEstimate("g1", size, window),)
    result = search(HoldSearchSettings(), BreakEvenWeights(), walking).run(
        inputs(load, transfers, headway)
    )
    decision = next(c for c in result.candidates if c.hold_s == result.hold_s)
    assert all(decision.net_ps >= c.net_ps for c in result.candidates)
    assert result.hold_s in HoldSearchSettings().candidates()
    # Holding only when it nets a strict gain
    assert (result.chosen is not None) == (decision.net_ps > 0)


def test_same_inputs_give_the_same_result():
    hold_search = search()
    first = hold_search.run(inputs(load=200))
    second = hold_search.run(inputs(load=200))
    assert first == second


def observation(trains):
    transfer = IncomingTransfer("g1", "green", 40, 120.0, 400.0, 90.0, 80)
    elsewhere = IncomingTransfer("g2", "rem", 50, 130.0, 400.0, 95.0, 70)
    return ObservationSnapshot(
        time_s=150.0,
        train_id="green_1",
        station_id="mcgill",
        platform_id="green",
        trains=trains,
        platforms=(),
        incoming_transfers=(transfer, elsewhere),
    )


def test_inputs_are_read_from_the_observation():
    train = TrainState("green_1", "green", None, None, None, 0.0, 420, 800)
    other = TrainState("rem_1", "rem", None, None, None, 0.0, 10, 780)
    built = HoldInputs.from_observation(observation((other, train)), headway_s=240.0)
    assert built == HoldInputs(
        150.0, "green_1", "mcgill", "green", 420, 240.0, (GROUP,)
    )


def test_inputs_need_the_deciding_train_in_the_observation():
    snapshot = observation(trains=())
    with pytest.raises(ValueError, match="no state for green_1"):
        HoldInputs.from_observation(snapshot, headway_s=240.0)


@pytest.mark.parametrize(
    ("load", "headway_s", "transfers", "message"),
    [
        (-1, 300.0, (), "load"),
        (100, -1.0, (), "headway_s"),
        (100, 300.0, [GROUP], "tuple"),
    ],
)
def test_inputs_reject_bad_values(load, headway_s, transfers, message):
    with pytest.raises(ValueError, match=message):
        HoldInputs(0.0, "green_1", "mcgill", "green", load, headway_s, transfers)
