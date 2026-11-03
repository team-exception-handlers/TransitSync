# AI contribution: 50% or more AI-generated
"""US-2.3 #48: test headway holding in the simulator, with all times in seconds.

Check actual departure gaps, fixed targets and inputs the policy must ignore.
"""

import dataclasses
from fractions import Fraction
from sys import float_info

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulator.control.interface import (
    HoldAction,
    IncomingTransfer,
    ObservationSnapshot,
    PlatformState,
    TrainState,
)
from simulator.control.strategies.headway_regulation import HeadwayRegulationStrategy


def snapshot(
    time_s: float = 280, last_departure_s: float | None = 100
) -> ObservationSnapshot:
    """Build a P1 departure decision with times in seconds.

    Put P2 first so tests catch code that uses the first platform by mistake.
    """
    return ObservationSnapshot(
        time_s=time_s,
        train_id="B",
        station_id="S1",
        platform_id="P1",
        scheduled_departure_s=280,
        trains=(),
        platforms=(
            PlatformState("P2", 0, None),
            PlatformState("P1", 0, last_departure_s),
        ),
        incoming_transfers=(),
    )


# A gap of 180 needs 120 seconds to reach 300; gaps of 300 or 420 need no hold.
# Quarter-seconds are exact in binary: 300.25 - 179.75 = 120.5 seconds.
@pytest.mark.parametrize(
    ("time_s", "last_departure_s", "target_s", "expected"),
    [
        (280, 100, 300, (HoldAction("B", 120, "headway_regulation"),)),
        (400, 100, 300, ()),
        (520, 100, 300, ()),
        (280, None, 300, ()),
        (180, 0, 300, (HoldAction("B", 120, "headway_regulation"),)),
        (280.25, 100.5, 300.25, (HoldAction("B", 120.5, "headway_regulation"),)),
        (280, 100, 240, (HoldAction("B", 60, "headway_regulation"),)),
        (100, 100, 300, (HoldAction("B", 300, "headway_regulation"),)),
    ],
    ids=[
        "below",
        "equal",
        "above",
        "first",
        "zero",
        "fractional",
        "target",
        "same_time",
    ],
)
def test_hold_uses_actual_platform_gap(time_s, last_departure_s, target_s, expected):
    """Check exact hold seconds below, at and above the target.

    Include departure at zero, no previous departure and a different target.
    These cases catch missing-history mistakes and a hard-coded target.
    """
    strategy = HeadwayRegulationStrategy({"P1": target_s, "P2": 900})
    observation = snapshot(time_s, last_departure_s)
    assert strategy.evaluate(observation) == expected


@pytest.mark.parametrize("other_departure_s", [None, 0, 280])
def test_unrelated_platform_history_does_not_change_hold(other_departure_s):
    """Keep P1's 120-second hold when P2's departure time changes.

    P2 has a different target, so reading its data would give the wrong hold.
    """
    observation = snapshot()
    observation = dataclasses.replace(
        observation,
        platforms=(
            PlatformState("P2", 900, other_departure_s),
            observation.platforms[1],
        ),
    )
    strategy = HeadwayRegulationStrategy({"P1": 300, "P2": 900})
    assert strategy.evaluate(observation) == (
        HoldAction("B", 120, "headway_regulation"),
    )


@pytest.mark.parametrize("scheduled_s", [100, 280, 400])
def test_timetable_does_not_change_headway_hold(scheduled_s):
    """Keep the 120-second hold for early, on-time and late timetables.

    This separates the headway rule from schedule-based holding.
    """
    observation = dataclasses.replace(snapshot(), scheduled_departure_s=scheduled_s)
    strategy = HeadwayRegulationStrategy({"P1": 300})
    assert strategy.evaluate(observation) == (
        HoldAction("B", 120, "headway_regulation"),
    )


@pytest.mark.parametrize("onboard_load", [0, 800])
@pytest.mark.parametrize("waiting_count", [0, 200])
@pytest.mark.parametrize(
    "transfers",
    [(), (IncomingTransfer("G", "P1", 200, 290, 320, 260, 200),)],
)
def test_passengers_do_not_change_or_mutate_decision(
    onboard_load, waiting_count, transfers
):
    """Keep the 120-second hold when passenger counts or transfers change.

    Vary each input separately so combined changes cannot hide a dependency.
    Also check that evaluating the policy leaves the observation unchanged.
    """
    observation = dataclasses.replace(
        snapshot(),
        trains=(TrainState("B", "rem", "P2", 600, 630, 120, onboard_load, 800),),
        platforms=(PlatformState("P1", waiting_count, 100),),
        incoming_transfers=transfers,
    )
    before = dataclasses.asdict(observation)
    strategy = HeadwayRegulationStrategy({"P1": 300})
    assert strategy.evaluate(observation) == (
        HoldAction("B", 120, "headway_regulation"),
    )
    assert dataclasses.asdict(observation) == before


@pytest.mark.parametrize("history", [None, 100])
@pytest.mark.parametrize("missing", ["platform", "target"])
def test_missing_deciding_platform_or_target_fails_clearly(history, missing):
    """Raise ValueError when P1 or its target is missing.

    Check before and after the first departure so validation cannot be skipped.
    """
    observation = snapshot(last_departure_s=history)
    targets = {"P2": 300}
    if missing == "platform":
        observation = dataclasses.replace(
            observation, platforms=observation.platforms[:1]
        )
        targets["P1"] = 300
    strategy = HeadwayRegulationStrategy(targets)
    with pytest.raises(ValueError, match=f"{missing}.*P1"):
        strategy.evaluate(observation)


@pytest.mark.parametrize("targets", [None, [], [("P1", 300)], "P1"])
def test_targets_require_a_mapping(targets):
    """Reject target inputs that are not mappings.

    Even a list of valid key/value pairs must fail rather than be converted.
    """
    with pytest.raises(ValueError, match="target_headways_s.*mapping"):
        HeadwayRegulationStrategy(targets)


@pytest.mark.parametrize("platform_id", ["", " ", 1, None])
def test_targets_reject_invalid_platform_ids(platform_id):
    """Raise ValueError for blank or non-text platform IDs."""
    targets = {platform_id: 300}
    with pytest.raises(ValueError, match="platform.*non-empty string"):
        HeadwayRegulationStrategy(targets)


@pytest.mark.parametrize(
    "target_s",
    [
        True,
        "300",
        None,
        0,
        -1,
        float("nan"),
        float("inf"),
        pytest.param(10**400, id="oversized_positive_integer"),
        pytest.param(-(10**400), id="oversized_negative_integer"),
        pytest.param(int(float_info.max) + 1, id="above_float_limit"),
        pytest.param(Fraction(10**400), id="oversized_real"),
        pytest.param(np.bool_(True), id="numpy_bool"),
        pytest.param(np.int64(0), id="numpy_zero"),
        pytest.param(np.float32("nan"), id="numpy_nan"),
        pytest.param(np.float64("inf"), id="numpy_inf"),
    ],
)
def test_targets_reject_invalid_seconds(target_s):
    """Reject invalid target seconds with a ValueError naming P1.

    Strings and booleans are not target numbers. Very large integers must also
    fail validation without leaking an OverflowError.
    """
    targets = {"P1": target_s}
    with pytest.raises(ValueError, match="P1.*finite.*positive"):
        HeadwayRegulationStrategy(targets)


@pytest.mark.parametrize("target_s", [float_info.max, int(float_info.max)])
def test_largest_representable_targets_remain_valid(target_s):
    """Accept the largest supported float and integer targets, in seconds.

    At a zero-second gap, the hold must equal the full target. This checks the
    valid upper boundary as well as the invalid values tested above.
    """
    strategy = HeadwayRegulationStrategy({"P1": target_s})
    observation = snapshot(0, 0)
    assert strategy.evaluate(observation) == (
        HoldAction("B", target_s, "headway_regulation"),
    )


@pytest.mark.parametrize(
    ("target", "hold", "number_type"),
    [
        (np.int64(300), 120, int),
        (np.float32(300.25), 120.25, float),
        (np.float64(300.25), 120.25, float),
    ],
)
def test_numpy_targets_produce_plain_number_holds(target, hold, number_type):
    """Accept NumPy numbers and store Python numbers for saving.

    The gap is 180 seconds: targets 300 and 300.25 need holds 120 and 120.25.
    Quarter seconds are exact, so no rounding tolerance is needed.
    """
    strategy = HeadwayRegulationStrategy({"P1": target})
    assert type(strategy.target_headways_s["P1"]) is number_type
    assert strategy.evaluate(snapshot()) == (
        HoldAction("B", hold, "headway_regulation"),
    )


def test_caller_changes_cannot_change_targets():
    """Keep the original target after the caller changes its dictionary.

    With a 180-second gap, sharing the changed target would request 720 seconds
    instead of 120.
    """
    targets = {"P1": 300}
    strategy = HeadwayRegulationStrategy(targets)
    targets["P1"] = 900
    observation = snapshot()
    assert strategy.evaluate(observation) == (
        HoldAction("B", 120, "headway_regulation"),
    )


def test_exposed_targets_cannot_be_mutated():
    """Raise TypeError when a caller tries to edit the stored targets."""
    strategy = HeadwayRegulationStrategy({"P1": 300})
    with pytest.raises(TypeError):
        strategy.target_headways_s["P1"] = 900


def test_targets_cannot_be_replaced():
    """Raise FrozenInstanceError when a caller tries to replace the targets."""
    strategy = HeadwayRegulationStrategy({"P1": 300})
    with pytest.raises(dataclasses.FrozenInstanceError):
        strategy.target_headways_s = {"P1": 900}


def test_repeated_decisions_use_each_train_and_platform():
    """Calculate a fresh hold for each train and platform.

    Different expected durations catch a reused answer from an earlier call.
    Train B is held twice, so a blanket one-hold-per-train limit would fail.
    """
    strategy = HeadwayRegulationStrategy({"P1": 300, "P2": 240})
    first = snapshot()
    second = dataclasses.replace(
        snapshot(460),
        train_id="C",
        platform_id="P2",
        platforms=(PlatformState("P2", 0, 280),),
    )
    third = snapshot(600, 400)
    assert strategy.evaluate(first) == (HoldAction("B", 120, "headway_regulation"),)
    # P2: 240 - (460 - 280) = 60; P1: 300 - (600 - 400) = 100.
    assert strategy.evaluate(second) == (HoldAction("C", 60, "headway_regulation"),)
    assert strategy.evaluate(third) == (HoldAction("B", 100, "headway_regulation"),)


@settings(max_examples=100, derandomize=True)
@given(
    previous=st.floats(min_value=0, max_value=86400, allow_nan=False),
    gap=st.floats(min_value=0, max_value=3600, allow_nan=False),
    target=st.floats(min_value=1, max_value=3600, allow_nan=False),
    extra_gap=st.floats(min_value=0, max_value=3600, allow_nan=False),
)
def test_holds_are_positive_and_nonincreasing_as_gap_grows(
    previous, gap, target, extra_gap
):
    """Check that a longer gap never needs a longer hold.

    No hold is needed once the gap reaches the target. The exact-value cases
    above check the arithmetic; this checks the rule across many finite gaps.
    """
    strategy = HeadwayRegulationStrategy({"P1": target})
    earlier = strategy.evaluate(snapshot(previous + gap, previous))
    later = strategy.evaluate(snapshot(previous + gap + extra_gap, previous))
    earlier_s = earlier[0].duration_s if earlier else 0
    later_s = later[0].duration_s if later else 0
    assert 0 <= later_s <= earlier_s <= target
    if earlier:
        assert earlier[0].duration_s > 0
    if later:
        assert later[0].duration_s > 0
