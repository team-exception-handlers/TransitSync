# AI contribution: 50% or more AI-generated
"""Matching one passenger across the selected-strategy and no-holding runs (#240)."""

import pytest

from api.passenger_outcomes import (
    PassengerComparison,
    PassengerOutcome,
    match_passengers,
)


def outcome(passenger_id, connection_id="link", **fields):
    return PassengerOutcome(
        passenger_id=passenger_id, connection_id=connection_id, alighting_s=0, **fields
    )


def test_passengers_are_paired_by_id_and_kept_when_in_one_run_only():
    held = [outcome("b", departure_s=40), outcome("a", departure_s=10)]
    baseline = [outcome("a", departure_s=70), outcome("c")]
    matched = match_passengers(held, baseline)

    assert [m.passenger_id for m in matched] == ["a", "b", "c"]
    assert matched[0].selected_strategy.departure_s == 10
    assert matched[0].without_holding.departure_s == 70
    # Edge: a passenger missing from one run keeps the other run's outcome
    assert matched[1].without_holding is None
    assert matched[1].selected_strategy.departure_s == 40
    assert matched[2].selected_strategy is None


@pytest.mark.parametrize(
    ("held", "baseline", "message"),
    [
        ([outcome("a"), outcome("a")], [], "repeat"),
        ([outcome("a")], [outcome("a", "other")], "two connections"),
    ],
)
def test_runs_that_are_not_a_pair_are_rejected(held, baseline, message):
    with pytest.raises(ValueError, match=message):
        match_passengers(held, baseline)


def test_comparison_serializes_the_matched_passengers():
    comparison = PassengerComparison(
        without_holding=[outcome("a", status="missed")],
        selected_strategy=[outcome("a", status="made")],
    ).model_dump()

    [matched] = comparison["matched_passengers"]
    assert matched["passenger_id"] == "a"
    assert matched["selected_strategy"]["status"] == "made"
    assert matched["without_holding"]["status"] == "missed"
