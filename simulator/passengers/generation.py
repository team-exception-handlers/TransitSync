# AI contribution: 50% or more AI-generated
"""

Modelling choice: batch counts are Poisson draws with mean equal to integrated
demand, and destinations are categorical draws from configured transfer fractions.
This module does not schedule arrivals. The caller (#18) requests a batch when a
feeder train arrives, then applies walking times (Mathematical Foundations §2).
"""

import math
from collections.abc import Mapping

from simulator.engine.random_streams import StreamManager
from simulator.passengers.demand import DemandProfile
from simulator.passengers.passenger import Passenger


def _destination_distribution(
    origin: str, transfer_fractions: Mapping[str, float]
) -> tuple[tuple[str, ...], tuple[float, ...]]:
    """Validate and canonicalise the complete destination distribution."""
    if not isinstance(origin, str) or not origin.strip():
        raise ValueError("origin must be a non-empty station identifier")
    if not isinstance(transfer_fractions, Mapping) or not transfer_fractions:
        raise ValueError("transfer_fractions must be a non-empty destination mapping")
    shares = []
    for destination, fraction in transfer_fractions.items():
        if not isinstance(destination, str) or not destination.strip():
            raise ValueError(
                "transfer_fractions destination must be a non-empty string"
            )
        if destination == origin:
            raise ValueError("transfer_fractions destination must differ from origin")
        if (
            isinstance(fraction, bool)
            or not isinstance(fraction, int | float)
            or not 0 <= fraction <= 1
        ):
            raise ValueError(
                "transfer_fractions values must be finite numbers in [0, 1]"
            )
        shares.append((destination, float(fraction)))
    total = math.fsum(fraction for _, fraction in shares)
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("transfer_fractions must sum to 1")
    shares.sort()
    # Normalise accepted floating-point roundoff before passing probabilities to NumPy.
    return (
        tuple(destination for destination, _ in shares),
        tuple(fraction / total for _, fraction in shares),
    )


class PassengerGenerator:
    """Create passenger batches with reproducible counts and destinations.

    Use one generator per run to keep IDs unique across origins and batches.
    Multiple generators need distinct ``id_prefix`` values. Time windows are
    supplied by the caller, which is responsible for avoiding double-counting
    demand across repeated or overlapping windows for the same passenger source.
    """

    def __init__(
        self, stream_manager: StreamManager, *, id_prefix: str = "passenger"
    ) -> None:
        if not isinstance(id_prefix, str) or not id_prefix.strip():
            raise ValueError("id_prefix must be a non-empty string")
        self._id_prefix = id_prefix
        self._next_id = 1
        self._count_stream = stream_manager.get_stream("group_sizes")
        self._destination_stream = stream_manager.get_stream("destinations")

    def generate(
        self,
        *,
        origin: str,
        demand_profile: DemandProfile,
        start_s: float,
        end_s: float,
        transfer_fractions: Mapping[str, float],
    ) -> list[Passenger]:
        """Generate one batch for a demand window measured in seconds.

        Fractions cover all modelled destinations and must sum to 1. A returned
        batch has no platform arrival timestamps: releasing and spreading it is
        the responsibility of task #18. All inputs are checked before RNG draws.
        """
        if not isinstance(demand_profile, DemandProfile):
            raise ValueError("demand_profile must be a DemandProfile")
        destinations, probabilities = _destination_distribution(
            origin, transfer_fractions
        )
        expected = demand_profile.expected_count(start_s, end_s)
        if expected == 0:
            return []
        try:
            count = int(self._count_stream.poisson(expected))
        except ValueError as error:
            raise ValueError(
                "demand_profile expected count is too large to sample"
            ) from error
        chosen = self._destination_stream.choice(
            destinations, size=count, p=probabilities
        )
        passengers = [
            Passenger(
                passenger_id=f"{self._id_prefix}-{self._next_id + index:06d}",
                origin=origin,
                destination=str(destination),
            )
            for index, destination in enumerate(chosen)
        ]
        self._next_id += count
        return passengers
