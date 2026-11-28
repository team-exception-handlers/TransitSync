# AI contribution: 50% or more AI-generated
"""Hand values and one bounded timing invariant for the #206 extraction."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulator.trains.departure_timing import departure_timing_s
from simulator.trains.suspension import LineSuspension


@pytest.mark.parametrize(
    ("ready_s", "origin", "previous_s", "intervals", "expected"),
    [
        (100, True, None, ((100, 200),), (200, 200)),
        (100, False, None, ((100, 200),), (100, 100)),
        (100, True, None, (), (100, 100)),
        (100, True, 52.5, (), (100, 142.5)),
        (99, True, 80, ((100, 200),), (99, 170)),
        (280, True, None, ((300, 450),), (280, 280)),
        (400, True, None, ((300, 450),), (450, 450)),
    ],
    ids=[
        "origin_dispatch",
        "intermediate_ignores_dispatch",
        "no_predecessor",
        "fractional_gap",
        "dispatch_before_gap",
        "before_later_suspension",
        "hold_enters_later_suspension",
    ],
)
def test_departure_timing_composes_dispatch_then_gap(
    ready_s, origin, previous_s, intervals, expected
):
    """Times are literal seconds; expected tuples are (dispatch, departure)."""
    suspensions = [LineSuspension("green", start, end) for start, end in intervals]

    # The gap row is 52.5 + 90 = 142.5. At readiness 99, dispatch is
    # allowed before the gap moves departure to 80 + 90 = 170.
    # The final pair adds 450 - 280 = 170 s for a requested 120 s hold.
    assert (
        departure_timing_s(
            ready_s,
            line_id="green",
            is_trip_origin=origin,
            suspensions=suspensions,
            previous_departure_s=previous_s,
            minimum_gap_s=90,
        )
        == expected
    )


@settings(max_examples=30, derandomize=True)
@given(
    readiness_ticks=st.integers(0, 2400),
    extra_ticks=st.integers(0, 800),
    previous_ticks=st.one_of(st.none(), st.integers(0, 2400)),
    gap_ticks=st.integers(0, 400),
    origin=st.booleans(),
)
def test_departure_timing_is_monotone_and_respects_floors(
    readiness_ticks, extra_ticks, previous_ticks, gap_ticks, origin
):
    """Quarter-second inputs stay exact and keep generated examples small."""
    ready_s = readiness_ticks / 4
    later_s = ready_s + extra_ticks / 4
    previous_s = None if previous_ticks is None else previous_ticks / 4
    gap_s = gap_ticks / 4
    restrictions = (
        LineSuspension("green", 100, 200),
        LineSuspension("green", 300, 450),
    )
    context = dict(
        line_id="green",
        is_trip_origin=origin,
        suspensions=restrictions,
        previous_departure_s=previous_s,
        minimum_gap_s=gap_s,
    )
    _, first_s = departure_timing_s(ready_s, **context)
    _, second_s = departure_timing_s(later_s, **context)

    assert first_s >= ready_s
    assert second_s >= later_s
    assert second_s >= first_s
    if previous_s is not None:
        assert first_s >= previous_s + gap_s
        assert second_s >= previous_s + gap_s
