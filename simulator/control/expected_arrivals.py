# AI contribution: 50% or more AI-generated
"""Expected passengers caught by a hold (US-2.2, Task 2.2.1, #41).

Implements N(h) = M * [F(h + s) - F(s)] from Mathematical Foundations
section 2. A hold of h seconds only catches the passengers who finish walking
after the train would have left, s seconds after their feeder arrived, and
before the hold ends. Using M * F(h + s) instead would also count people who
connect without any hold.

``s`` is measured to the decision time, when the train is ready to leave. That
is the time already elapsed since the feeding train arrived, and differs from
the scheduled departure when the departing train is late.

M is the group size the controller observes. Once the error model (#39) is in
place that is an estimate, so this module never sees the true group size.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from simulator.control.interface import IncomingTransfer, ObservationSnapshot
from simulator.control.validation import finite_number
from simulator.control.walking_cdf import WalkingCdf


@dataclass(frozen=True, slots=True)
class TransferEstimate:
    """What the decision engine knows about one walking transfer group.

    ``group_size`` is M in passengers. ``conn_window_s`` is s in seconds:
    decision time minus feeder arrival. It is negative when the feeder has
    not arrived yet, and then F(s) = 0 so the whole group is still to come.
    Raises ``ValueError`` for a negative or non-numeric M, or a non-finite s.
    """

    group_id: str
    group_size: float
    conn_window_s: float

    def __post_init__(self) -> None:
        finite_number("TransferEstimate.group_size", self.group_size, 0.0)
        finite_number("TransferEstimate.conn_window_s", self.conn_window_s)

    @classmethod
    def from_incoming(
        cls, transfer: IncomingTransfer, decision_time_s: float
    ) -> "TransferEstimate":
        """Build the estimate for ``transfer`` at ``decision_time_s`` seconds."""
        return cls(
            group_id=transfer.group_id,
            group_size=transfer.group_size,
            conn_window_s=decision_time_s - transfer.feeder_arrival_s,
        )


def transfers_to_platform(
    observation: ObservationSnapshot,
) -> tuple[TransferEstimate, ...]:
    """Return the groups walking to the deciding train's platform.

    Groups heading to other platforms cannot board this train, so a hold here
    catches none of them.
    """
    return tuple(
        TransferEstimate.from_incoming(transfer, observation.time_s)
        for transfer in observation.incoming_transfers
        if transfer.platform_id == observation.platform_id
    )


def caught_fraction(conn_window_s: float, hold_s: float, walking: WalkingCdf) -> float:
    """Return F(h + s) - F(s): the share of a group a hold of ``hold_s`` catches.

    Args:
        conn_window_s: s, seconds from feeder arrival to the decision.
        hold_s: h, hold length in seconds, at least 0.
        walking: the walking-time CDF F.

    Raises:
        ValueError: ``hold_s`` is negative or either time is not finite.
    """
    window = finite_number("conn_window_s", conn_window_s)
    hold = finite_number("hold_s", hold_s, 0.0)
    return walking.cdf(window + hold) - walking.cdf(window)


def expected_caught(
    group_size: float, conn_window_s: float, hold_s: float, walking: WalkingCdf
) -> float:
    """Return N(h) = M * [F(h + s) - F(s)] in passengers for one group.

    Args:
        group_size: M, the observed (estimated) group size in passengers.
        conn_window_s: s in seconds; see ``TransferEstimate``.
        hold_s: h, hold length in seconds, at least 0.
        walking: the walking-time CDF F.

    Raises:
        ValueError: M or ``hold_s`` is negative, or any input is not finite.
    """
    size = finite_number("group_size", group_size, 0.0)
    return size * caught_fraction(conn_window_s, hold_s, walking)


def total_expected_caught(
    transfers: Iterable[TransferEstimate], hold_s: float, walking: WalkingCdf
) -> float:
    """Return N(h) summed over every group walking to the platform.

    Each group has its own feeder arrival, so each has its own s. Groups are
    independent, so the expected counts add.
    """
    return sum(
        expected_caught(group.group_size, group.conn_window_s, hold_s, walking)
        for group in transfers
    )
