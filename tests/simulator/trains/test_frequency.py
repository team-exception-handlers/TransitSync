# AI contribution: 50% or more AI-generated
"""Re-timing the connecting line to a chosen headway (#259)."""

from itertools import pairwise

import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.trains.frequency import retime_line
from simulator.trains.train import ScheduledStop, Train


def _train(train_id, platform_id, arrival_s, departure_s, line_id="1", load=300):
    stop = ScheduledStop("32", platform_id, arrival_s, departure_s)
    return Train(
        id=train_id,
        capacity=800,
        schedule=(stop,),
        line_id=line_id,
        onboard_load=load,
    )


def test_copies_of_the_first_train_leave_every_headway():
    # Timetable: 100 s, 250 s, 500 s. First departure 100 s, h = 300 s, run
    # 1000 s: copies at 100, 400, 700 (1000 is the end, so not included)
    trains = [
        _train("late", "green_0", 470, 500),
        _train("first", "green_0", 70, 100),
        _train("second", "green_0", 220, 250),
    ]
    retimed = retime_line(trains, "green_0", 300, 1000)
    assert [t.id for t in retimed] == ["first:h0", "first:h1", "first:h2"]
    assert [t.schedule[0].departure_s for t in retimed] == [100, 400, 700]
    # The 30 s dwell and the template's load carry over to every copy
    assert [t.schedule[0].arrival_s for t in retimed] == [70, 370, 670]
    assert {t.onboard_load for t in retimed} == {300}


def test_trains_on_other_platforms_keep_their_timetable():
    rem = _train("rem", "rem_0", 50, 80, line_id="S1")
    green = _train("green", "green_0", 70, 100)
    retimed = retime_line([rem, green], "green_0", 600, 1000)
    assert retimed[0] is rem
    assert [t.id for t in retimed[1:]] == ["green:h0", "green:h1"]


def test_shorter_headway_adds_trains_beyond_the_timetable():
    trains = [_train("only", "green_0", 0, 30)]
    retimed = retime_line(trains, "green_0", 120, 3600)
    # ceil((3600 - 30) / 120) = 30 trains from a one-train timetable
    assert len(retimed) == 30
    assert retimed[-1].schedule[0].departure_s == 30 + 29 * 120


def test_a_template_after_the_run_end_is_still_kept():
    retimed = retime_line([_train("t", "green_0", 990, 1020)], "green_0", 300, 1000)
    assert [t.id for t in retimed] == ["t:h0"]


@pytest.mark.parametrize("headway", [0, -60, float("nan")])
def test_rejects_a_headway_that_is_not_positive(headway):
    with pytest.raises(ValueError, match="headway_s must be a positive"):
        retime_line([_train("t", "green_0", 0, 30)], "green_0", headway, 1000)


def test_rejects_a_platform_no_train_serves():
    with pytest.raises(ValueError, match="No train serves platform blue_0"):
        retime_line([_train("t", "green_0", 0, 30)], "blue_0", 180, 1000)


@given(
    headway=st.integers(min_value=120, max_value=600),
    first=st.integers(min_value=0, max_value=900),
)
def test_consecutive_departures_are_exactly_one_headway_apart(headway, first):
    """Property: the platform always sees the chosen gap, never anything else."""
    retimed = retime_line(
        [_train("t", "green_0", first, first + 30)], "green_0", headway, 3600
    )
    departures = [t.schedule[0].departure_s for t in retimed]
    assert all(b - a == headway for a, b in pairwise(departures))
    assert departures[0] == first + 30
