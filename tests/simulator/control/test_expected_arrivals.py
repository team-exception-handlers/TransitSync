# AI contribution: 50% or more AI-generated
"""Tests for expected passengers caught by a hold (US-2.2, Task 2.2.1, #41).

Hand values use the simulator's default walk: shifted exponential, mean 300 s,
minimum 30 s, so F(t) = 1 - exp(-(t - 30) / 270) for t >= 30.
"""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.control.expected_arrivals import (
    TransferEstimate,
    caught_fraction,
    expected_caught,
    total_expected_caught,
    transfers_to_platform,
)
from simulator.control.interface import IncomingTransfer, ObservationSnapshot
from simulator.control.walking_cdf import LognormalCdf, ShiftedExponentialCdf

WALK = ShiftedExponentialCdf(mean_s=300.0, min_s=30.0)


class TableCdf:
    """F given only at the points of the wiki's section 2 example."""

    values = {90.0: 0.45, 120.0: 0.70}

    def cdf(self, t_s):
        return self.values[t_s]


def incoming(group_id, platform_id, feeder_arrival_s, group_size):
    return IncomingTransfer(
        group_id=group_id,
        platform_id=platform_id,
        passenger_count=group_size,
        first_arrival_s=feeder_arrival_s + 30.0,
        last_arrival_s=feeder_arrival_s + 400.0,
        feeder_arrival_s=feeder_arrival_s,
        group_size=group_size,
    )


def snapshot(*transfers):
    return ObservationSnapshot(
        time_s=300.0,
        train_id="green_0001",
        station_id="mcgill",
        platform_id="green_mcgill_0",
        trains=(),
        platforms=(),
        incoming_transfers=transfers,
    )


def test_wiki_example_hold_of_30_s_catches_15():
    # M = 60, s = 90: 60 * (F(120) - F(90)) = 60 * (0.70 - 0.45) = 15
    assert expected_caught(60, 90.0, 30.0, TableCdf()) == pytest.approx(15.0)


def test_caught_matches_hand_value():
    # 100 * (F(90) - F(60)) = 100 * (exp(-1/9) - exp(-2/9)) = 9.410191
    assert expected_caught(100, 60.0, 30.0, WALK) == pytest.approx(9.410191, abs=1e-6)


def test_lognormal_caught_matches_hand_value():
    # Median 110 s, sigma 0.5. s = 110 and s + h = 110 e^0.5, so
    # N = 60 * (Phi(1) - Phi(0)) = 60 * (0.841345 - 0.5) = 20.480685
    walking = LognormalCdf(mu=math.log(110.0), sigma=0.5)
    hold_s = 110.0 * (math.exp(0.5) - 1.0)
    caught = expected_caught(60, 110.0, hold_s, walking)
    assert caught == pytest.approx(20.480685, abs=1e-6)


@pytest.mark.parametrize(
    ("conn_window_s", "expected"),
    [
        # s = 0: F(60) - F(0) = 1 - exp(-1/9) = 0.105161
        (0.0, 10.516068),
        # s = 60: F(120) - F(60) = exp(-1/9) - exp(-1/3) = 0.178308
        (60.0, 17.830801),
        # Feeder 30 s away: F(30) - F(-30) = 0, nobody walks in under 30 s
        (-30.0, 0.0),
    ],
)
def test_elapsed_time_since_feeder_arrival_shifts_the_result(conn_window_s, expected):
    caught = expected_caught(100, conn_window_s, 60.0, WALK)
    assert caught == pytest.approx(expected, abs=1e-6)


def test_hold_shorter_than_the_fastest_walk_catches_nobody():
    # Feeder just arrived and the hold ends at 30 s, the minimum walk
    assert expected_caught(100, 0.0, 30.0, WALK) == 0.0


@given(
    size=st.integers(min_value=0, max_value=1000),
    window=st.floats(min_value=-300.0, max_value=1200.0),
)
def test_zero_hold_catches_zero_passengers(size, window):
    assert expected_caught(size, window, 0.0, WALK) == 0.0


@given(
    window=st.floats(min_value=-300.0, max_value=1200.0),
    first=st.floats(min_value=0.0, max_value=600.0),
    second=st.floats(min_value=0.0, max_value=600.0),
)
def test_caught_never_decreases_with_a_longer_hold(window, first, second):
    shorter, longer = sorted((first, second))
    assert expected_caught(80, window, shorter, WALK) <= expected_caught(
        80, window, longer, WALK
    )


@given(window=st.floats(min_value=-300.0, max_value=1200.0))
def test_caught_levels_off_at_everyone_still_walking(window):
    # A very long hold catches every passenger who has not arrived by s
    still_walking = 80 * (1.0 - WALK.cdf(window))
    caught = expected_caught(80, window, 1e6, WALK)
    assert caught == pytest.approx(still_walking)


def test_each_extra_step_catches_fewer_passengers_once_the_bulk_has_arrived():
    caught = [expected_caught(100, 60.0, hold, WALK) for hold in (0, 30, 60, 90)]
    gains = [after - before for before, after in zip(caught, caught[1:], strict=False)]
    assert gains == sorted(gains, reverse=True)


def test_same_inputs_give_the_same_output():
    first = expected_caught(100, 60.0, 30.0, WALK)
    second = expected_caught(100, 60.0, 30.0, WALK)
    assert first == second


def test_fraction_is_the_count_divided_by_the_group_size():
    fraction = caught_fraction(60.0, 30.0, WALK)
    assert expected_caught(100, 60.0, 30.0, WALK) == pytest.approx(100 * fraction)


@pytest.mark.parametrize(
    ("group_size", "conn_window_s", "hold_s", "message"),
    [
        (-1, 60.0, 30.0, "group_size"),
        (100, 60.0, -5.0, "hold_s"),
        (100, math.nan, 30.0, "conn_window_s"),
        (100, 60.0, math.inf, "hold_s"),
        (True, 60.0, 30.0, "group_size"),
    ],
)
def test_expected_caught_rejects_bad_input(group_size, conn_window_s, hold_s, message):
    with pytest.raises(ValueError, match=message):
        expected_caught(group_size, conn_window_s, hold_s, WALK)


def test_estimate_measures_the_window_from_feeder_arrival_to_the_decision():
    transfer = incoming("g1", "green_mcgill_0", feeder_arrival_s=240.0, group_size=50)
    estimate = TransferEstimate.from_incoming(transfer, decision_time_s=300.0)
    assert estimate == TransferEstimate("g1", 50, 60.0)


def test_estimate_uses_the_whole_group_not_only_those_still_walking():
    transfer = IncomingTransfer("g1", "green_mcgill_0", 4, 310.0, 400.0, 240.0, 50)
    estimate = TransferEstimate.from_incoming(transfer, decision_time_s=300.0)
    assert estimate.group_size == 50


def test_only_groups_walking_to_the_deciding_platform_are_counted():
    mine = incoming("g1", "green_mcgill_0", 240.0, 50)
    other = incoming("g2", "rem_mcgill_0", 250.0, 70)
    estimates = transfers_to_platform(snapshot(mine, other))
    assert estimates == (TransferEstimate("g1", 50, 60.0),)


def test_total_adds_each_group_with_its_own_window():
    groups = (TransferEstimate("g1", 100, 60.0), TransferEstimate("g2", 100, 0.0))
    # 17.830801 + 10.516068 from the hand values above
    total = total_expected_caught(groups, 60.0, WALK)
    assert total == pytest.approx(28.346869, abs=1e-6)


def test_total_with_no_groups_is_zero():
    assert total_expected_caught((), 60.0, WALK) == 0


def test_estimate_rejects_a_negative_group_size():
    with pytest.raises(ValueError, match="group_size"):
        TransferEstimate("g1", -3, 60.0)
