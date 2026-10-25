# AI contribution: 50% or more AI-generated
"""Train schedule, return trip and delay breakdown validation."""

import pytest

from simulator.trains.train import ScheduledStop, Train

OUTBOUND = (ScheduledStop("A", "A-out", 0, 10), ScheduledStop("B", "B-in", 100, 100))


def train(**overrides):
    return Train("t", 100, overrides.pop("schedule", OUTBOUND), **overrides)


def test_out_of_order_schedule_is_rejected():
    backwards = (ScheduledStop("A", "A", 0, 50), ScheduledStop("B", "B", 40, 40))
    with pytest.raises(ValueError, match="Train stops must be chronological"):
        train(schedule=backwards)


@pytest.mark.parametrize(
    "trip,message",
    [
        ((), "Return trips cannot be empty"),
        (
            (ScheduledStop("B", "B-out", 200, 250), ScheduledStop("A", "A", 240, 240)),
            "Train stops must be chronological",
        ),
        ((ScheduledStop("C", "C", 200, 200),), "previous terminus"),
        ((ScheduledStop("B", "B-out", 100, 100),), "gap must be positive"),
        ((ScheduledStop("B", "B-out", 130, 130),), "cover slack"),
    ],
)
def test_invalid_return_trip_names_the_problem(trip, message):
    with pytest.raises(ValueError, match=message):
        train(layover_slack=60, return_trips=(trip,))


def test_return_trip_gap_equal_to_slack_is_accepted():
    trip = (ScheduledStop("B", "B-out", 160, 160),)
    assert train(layover_slack=60, return_trips=(trip,)).return_trips == (trip,)


@pytest.mark.parametrize(
    "delays,message",
    [
        (dict(generated_delay_s=-1.0), "Delay components"),
        (dict(inherited_delay_s=float("nan")), "Delay components"),
        (dict(current_delay=30.0, generated_delay_s=10.0), "breakdown"),
    ],
)
def test_invalid_delay_breakdown_is_rejected(delays, message):
    with pytest.raises(ValueError, match=message):
        train(**delays)


def test_delay_split_between_generated_and_inherited_is_accepted():
    split = train(current_delay=30.0, generated_delay_s=10.0, inherited_delay_s=20.0)
    assert split.generated_delay_s + split.inherited_delay_s == 30.0
