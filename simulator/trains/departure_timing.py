# AI contribution: 50% or more AI-generated
"""Share existing train departure constraints for #206 (US-2.4)."""

from collections.abc import Sequence

from simulator.trains.suspension import LineSuspension, dispatch_ready_s


def departure_timing_s(
    ready_s: float,
    *,
    line_id: str,
    is_trip_origin: bool,
    suspensions: Sequence[LineSuspension],
    previous_departure_s: float | None,
    minimum_gap_s: float,
) -> tuple[float, float]:
    """Return (dispatch, gap-cleared departure) in seconds from validated state.
    None means no predecessor. Origins check dispatch before the gap, which
    never reapplies dispatch; clock floors remain in the engine handlers.
    """
    dispatch_s = ready_s
    if is_trip_origin:
        dispatch_s = dispatch_ready_s(line_id, ready_s, suspensions)
    departure_s = dispatch_s
    if previous_departure_s is not None:
        departure_s = max(dispatch_s, previous_departure_s + minimum_gap_s)
    return dispatch_s, departure_s
