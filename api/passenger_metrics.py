# AI contribution: 50% or more AI-generated
"""Connection statistics for the transfer passengers in one simulation run."""

from collections.abc import Sequence
from statistics import fmean

from pydantic import BaseModel

from api.passenger_outcomes import PassengerOutcome


class PassengerMetrics(BaseModel):
    """Pending transfers count toward the total. Unobserved averages are null."""

    total_affected_passengers: int
    successful_connections: int
    missed_connections: int
    average_transfer_time_s: float | None
    average_passenger_delay_s: float | None


def compute_passenger_metrics(outcomes: Sequence[PassengerOutcome]) -> PassengerMetrics:
    """Count each passenger once and average each duration over its known values."""
    transfer_times = [
        p.transfer_time_s for p in outcomes if p.transfer_time_s is not None
    ]
    delays = [p.delay_s for p in outcomes if p.delay_s is not None]
    return PassengerMetrics(
        total_affected_passengers=len(outcomes),
        successful_connections=sum(p.status == "made" for p in outcomes),
        missed_connections=sum(p.status == "missed" for p in outcomes),
        average_transfer_time_s=fmean(transfer_times) if transfer_times else None,
        average_passenger_delay_s=fmean(delays) if delays else None,
    )
