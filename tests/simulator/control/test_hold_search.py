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
from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulator.control.break_even import BreakEvenWeights
from simulator.control.expected_arrivals import TransferEstimate, total_expected_caught
from simulator.control.hold_search import (
    MAX_CANDIDATES,
    HoldInputs,
    HoldSearch,
    HoldSearchSettings,
)
from simulator.control.interface import (
    CurrentVisitState,
    IncomingTransfer,
    ObservationSnapshot,
    PlatformState,
    TrainState,
)
from simulator.control.walking_cdf import ShiftedExponentialCdf
from simulator.trains.suspension import LineSuspension

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


@settings(max_examples=30, derandomize=True)
@given(
    clearance=st.one_of(st.none(), st.integers(min_value=0, max_value=400)),
    load=st.integers(min_value=0, max_value=1500),
    size=st.integers(min_value=0, max_value=400),
    window=st.floats(min_value=-120.0, max_value=600.0),
    headway=st.floats(min_value=60.0, max_value=900.0),
)
def test_chosen_hold_is_never_beaten_and_stays_in_range(
    load, size, window, headway, clearance
):
    walking = ShiftedExponentialCdf(mean_s=300.0, min_s=30.0)
    transfers = (TransferEstimate("g1", size, window),)
    built = inputs(load, transfers, headway)
    context = None
    if clearance is not None:
        built, context = clearance_inputs(previous_s=clearance / 4)
        built = replace(built, load=load, transfers=transfers, headway_s=headway)
    result = search(HoldSearchSettings(), BreakEvenWeights(), walking).run(
        built, departure_context=context
    )
    decision = next(c for c in result.candidates if c.hold_s == result.hold_s)
    assert [c.hold_s for c in result.candidates] == list(range(0, 61, 5))
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
    transfer = IncomingTransfer("g1", "green", 40, 120.0, 400.0, 100.0, 60)
    elsewhere = IncomingTransfer("g2", "rem", 50, 130.0, 400.0, 95.0, 70)
    return ObservationSnapshot(
        time_s=220.0,
        train_id="green_1",
        station_id="mcgill",
        platform_id="green",
        scheduled_departure_s=190.0,
        trains=trains,
        platforms=(),
        incoming_transfers=(transfer, elsewhere),
    )


def test_inputs_are_read_from_the_observation():
    class LateDecisionCdf:
        """Give the share of passengers who finish walking by each time in seconds."""

        def cdf(self, t_s):
            return {90.0: 0.25, 120.0: 0.75, 150.0: 0.875}[t_s]

    train = TrainState("green_1", "green", None, None, None, 0.0, 420, 800)
    other = TrainState("rem_1", "rem", None, None, None, 0.0, 10, 780)
    built = HoldInputs.from_observation(observation((other, train)), headway_s=240.0)
    assert built == HoldInputs(
        220.0,
        "green_1",
        "mcgill",
        "green",
        420,
        240.0,
        (TransferEstimate("g1", 60, 120.0),),
    )
    # At the decision, 120 s have passed since the feeder arrived (220 - 100).
    # Another 30 s catches 60 * (0.875 - 0.75) = 7.5 more passengers.
    # Using the schedule instead gives 90 s and wrongly counts 30 passengers.
    # These values have no rounding error, so we can check the exact result.
    assert total_expected_caught(built.transfers, 30.0, LateDecisionCdf()) == 7.5


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


class UniformCdf:
    """Spread walking times evenly from zero to end_s seconds for simple arithmetic."""

    def __init__(self, end_s=200):
        self.end_s = end_s

    def cdf(self, t_s):
        return min(1, max(0, t_s / self.end_s))


def clearance_inputs(ready_s=100, previous_s=50, suspensions=()):
    """Build search inputs and a snapshot of the train's current restrictions."""
    context = ObservationSnapshot(
        ready_s,
        "green_1",
        "mcgill",
        "green",
        ready_s,
        (TrainState("green_1", "green", None, None, None, 0, 100, 800),),
        (PlatformState("rem", 0, 30), PlatformState("green", 0, previous_s)),
        (IncomingTransfer("g1", "green", 100, 0, 500, 0, 100),),
        current_visit=CurrentVisitState("green", True),
        suspensions=suspensions,
    )
    return HoldInputs.from_observation(context, 300), context


@pytest.mark.parametrize(
    (
        "ready",
        "previous",
        "closures",
        "hold",
        "end",
        "d0",
        "departure",
        "caught",
        "benefit",
        "cost",
        "net",
    ),
    [
        (100, 50, (), 30, 200, 140, 140, 0, 0, 0, 0),
        (100, 50, (), 40, 200, 140, 140, 0, 0, 0, 0),
        (100, 50, (), 60, 200, 140, 160, 10, 3000, 2000, 1000),
        # 52.5 + 90 = 142.5: retain the original five-second request grid.
        (100, 52.5, (), 40, 200, 142.5, 142.5, 0, 0, 0, 0),
        (100, 52.5, (), 45, 200, 142.5, 145, 1.25, 375, 250, 125),
        (100, None, (), 60, 200, 100, 160, 30, 9000, 6000, 3000),
        (
            280,
            None,
            (LineSuspension("green", 300, 450),),
            120,
            500,
            280,
            450,
            34,
            10200,
            17000,
            -6800,
        ),
    ],
)
def test_clearance_economics_use_projected_departure_endpoints(
    ready, previous, closures, hold, end, d0, departure, caught, benefit, cost, net
):
    built, context = clearance_inputs(ready, previous, closures)
    result = HoldSearch(UniformCdf(end), EQUAL, HoldSearchSettings(5, hold)).run(
        built, departure_context=context
    )
    assert [c.hold_s for c in result.candidates] == list(range(0, hold + 1, 5))
    candidate = result.candidates[-1]
    assert result.no_hold_departure_s == d0
    assert candidate.hold_s == hold
    assert candidate.departure_s == departure
    assert candidate.incremental_delay_s == departure - d0
    # Group size 100, headway 300 s, onboard load 100, both weights 1.
    # Tolerances allow only rounding in the walking-time probabilities.
    assert candidate.n_caught == pytest.approx(caught, abs=1e-9, rel=0)
    assert candidate.benefit_ps == pytest.approx(benefit, abs=1e-6, rel=0)
    assert candidate.cost_ps == pytest.approx(cost, abs=1e-6, rel=0)
    assert candidate.net_ps == pytest.approx(net, abs=1e-6, rel=0)


@pytest.mark.parametrize(
    ("previous_s", "no_hold_s", "cost", "net", "longer_cost", "longer_net"),
    [(50, 140, 1000, 14000, 2000, 13000), (52.5, 142.5, 750, 14250, 1750, 13250)],
)
def test_nonlinear_burst_excludes_connections_during_mandatory_wait(
    previous_s, no_hold_s, cost, net, longer_cost, longer_net
):
    class PulseCdf:
        def cdf(self, t_s):
            return 0.5 * (t_s >= 130) + 0.5 * (t_s >= 150)

    built, context = clearance_inputs(previous_s=previous_s)
    result = HoldSearch(PulseCdf(), EQUAL).run(built, departure_context=context)
    # Half the group arrives at 130 s and already connects without a hold.
    # Request 50 catches the other 50 at 150 s: benefit = 50*300 = 15000 pax-s.
    # At D0=142.5, cost = 100*7.5 = 750; request 60 costs 100*17.5 = 1750.
    # At D0=140, the same requests cost 1000 and 2000 respectively.
    assert result.no_hold_departure_s == no_hold_s
    assert [c.hold_s for c in result.candidates] == list(range(0, 61, 5))
    assert result.hold_s == 50
    assert result.chosen.departure_s == 150
    assert result.chosen.incremental_delay_s == 150 - no_hold_s
    assert result.chosen.n_caught == 50
    assert result.chosen.benefit_ps == 15000
    assert result.chosen.cost_ps == cost
    assert result.chosen.net_ps == net
    longer = result.candidates[-1]
    assert longer.hold_s == 60
    assert longer.n_caught == 50
    assert longer.cost_ps == longer_cost
    assert longer.net_ps == longer_net


def test_fully_absorbed_holds_decline_even_with_zero_load():
    built, context = clearance_inputs(previous_s=110)
    result = HoldSearch(UniformCdf(), EQUAL).run(
        replace(built, load=0), departure_context=context
    )
    assert result.hold_s == 0
    assert all(c.n_caught == 0 for c in result.candidates)


def test_departure_context_must_match_the_deciding_visit():
    built, context = clearance_inputs()
    other = replace(context, platform_id="rem")
    hold_search = HoldSearch(UniformCdf())
    with pytest.raises(ValueError, match="match the deciding visit"):
        hold_search.run(built, departure_context=other)


def test_clearance_search_declines_at_exact_break_even():
    """Equal passenger benefit and onboard cost must leave h=0 selected."""
    built, context = clearance_inputs()
    result = HoldSearch(UniformCdf(160), EQUAL, HoldSearchSettings(5, 60)).run(
        replace(built, load=187.5), departure_context=context
    )
    # F(140)=0.875 and F(160)=1 are exact in binary: no rounding hides a tie.
    # 12.5 passengers * 300 = 187.5 onboard * 20 = 3750 pax-s.
    assert result.candidates[-1].benefit_ps == 3750
    assert result.candidates[-1].cost_ps == 3750
    assert result.candidates[0].hold_s == 0
    assert result.hold_s == 0
