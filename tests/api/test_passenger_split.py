# AI contribution: 50% or more AI-generated
"""Better off, worse off and unaffected passengers with a 30 s threshold (#284)."""

import pytest

from api.passenger_outcomes import MatchedPassenger, PassengerOutcome
from api.passenger_split import classify, split_passengers

RUN_END_S = 1000


def side(departure_s):
    return PassengerOutcome(
        passenger_id="p", connection_id="link", alighting_s=0, departure_s=departure_s
    )


def pair(held_s, baseline_s, *, missing=False):
    """A passenger leaving at held_s with holding and baseline_s without (s)."""
    return MatchedPassenger(
        passenger_id="p",
        selected_strategy=None if missing else side(held_s),
        without_holding=side(baseline_s),
    )


@pytest.mark.parametrize(
    ("difference", "group"),
    [
        (-120, "better_off"),
        (-30.5, "better_off"),
        (-30, "unaffected"),
        (0, "unaffected"),
        (30, "unaffected"),
        (30.5, "worse_off"),
    ],
)
def test_threshold_boundaries(difference, group):
    assert classify(difference) == group


def test_split_counts_groups_and_averages_saved_and_lost_time():
    # D = held - baseline: -120 and -40 saved; -30, 0 and 30 unaffected;
    # 31 and 90 lost. Saved 120 + 40 = 160 (mean 80), lost 31 + 90 = 121 (60.5).
    # Leaving in neither run or missing from one is not compared
    matched = [
        pair(380, 500),
        pair(460, 500),
        pair(470, 500),
        pair(500, 500),
        pair(530, 500),
        pair(531, 500),
        pair(590, 500),
        pair(None, None),
        pair(400, 500, missing=True),
    ]
    split = split_passengers(matched, RUN_END_S)

    assert (split.better_off, split.worse_off, split.unaffected) == (2, 2, 3)
    assert split.not_compared == 2
    assert split.left_in_one_run == 0
    # Sent with the split, so the Compare screen uses the same threshold
    assert split.unaffected_threshold_s == 30
    assert split.total_time_saved_s == 160
    assert split.average_time_saved_s == 80
    assert split.total_time_lost_s == 121
    assert split.average_time_lost_s == 60.5


def test_no_comparable_passengers_gives_zero_counts_and_no_averages():
    split = split_passengers([pair(None, None)], RUN_END_S)

    assert (split.better_off, split.worse_off, split.unaffected) == (0, 0, 0)
    assert split.not_compared == 1
    assert split.total_time_saved_s == split.total_time_lost_s == 0
    assert split.average_time_saved_s is split.average_time_lost_s is None


def test_leaving_in_one_run_only_uses_the_run_end_for_the_other_run():
    # Run end 1000 s. Left at 700 s with holding only: D = 700 - 1000 = -300,
    # better off. Left at 900 s without holding only: D = 1000 - 900 = 100,
    # worse off. Left at 990 s with holding only: D = -10, unaffected as far as
    # the run can tell (review on #418)
    matched = [pair(700, None), pair(None, 900), pair(990, None)]
    split = split_passengers(matched, RUN_END_S)

    assert (split.better_off, split.worse_off, split.unaffected) == (1, 1, 1)
    assert split.left_in_one_run == 3
    assert split.not_compared == 0
    assert split.total_time_saved_s == 300
    assert split.total_time_lost_s == 100
