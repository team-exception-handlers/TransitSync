# AI contribution: 50% or more AI-generated
"""Check passenger counts and independent denominators for observed times."""

import pytest

from api.passenger_metrics import compute_passenger_metrics
from api.passenger_outcomes import PassengerOutcome


def outcome(passenger_id, **fields):
    return PassengerOutcome(
        passenger_id=passenger_id, connection_id="mcgill", alighting_s=0, **fields
    )


def test_counts_passengers_and_averages_only_observed_values():
    outcomes = [
        outcome("first", status="made", transfer_time_s=10, delay_s=0),
        outcome(
            "later",
            status="missed",
            missed_train_ids=["a", "b"],
            transfer_time_s=50,
            delay_s=20,
        ),
        outcome("aboard", status="missed", transfer_time_s=15),
        outcome("still_waiting", status="missed", missed_train_ids=["a"]),
        outcome("walking"),
    ]
    assert compute_passenger_metrics(outcomes).model_dump() == {
        "total_affected_passengers": 5,
        "successful_connections": 1,
        "missed_connections": 3,
        "average_transfer_time_s": 25,
        "average_passenger_delay_s": 10,
    }


@pytest.mark.parametrize("outcomes", [[], [outcome("walking")]])
def test_missing_observations_have_null_averages(outcomes):
    metrics = compute_passenger_metrics(outcomes)
    assert metrics.total_affected_passengers == len(outcomes)
    assert metrics.successful_connections == metrics.missed_connections == 0
    assert metrics.average_transfer_time_s is metrics.average_passenger_delay_s is None
