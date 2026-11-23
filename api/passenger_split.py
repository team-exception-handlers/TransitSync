# AI contribution: 50% or more AI-generated
"""Passengers helped or harmed by holding, from matched paired outcomes (#284).

For each passenger D = Y_hold - Y_no_hold (Mathematical Foundations section 9),
where Y is when they left the interchange on their connecting train. Negative
D means holding got them out sooner. Changes within the threshold are noise.
"""

import math
from collections.abc import Sequence
from statistics import fmean
from typing import Literal

from pydantic import BaseModel, Field

from api.passenger_outcomes import MatchedPassenger

# US-6.3 threshold: a change of 30 s or less counts as unaffected
UNAFFECTED_THRESHOLD_S = 30.0

Group = Literal["better_off", "worse_off", "unaffected"]


class PassengerSplit(BaseModel):
    """Group counts and the time each changed group gained or lost, in seconds."""

    better_off: int
    worse_off: int
    unaffected: int
    not_compared: int = Field(
        description="Passengers without a departure in one of the runs, so D is unknown"
    )
    total_time_saved_s: float
    total_time_lost_s: float
    average_time_saved_s: float | None
    average_time_lost_s: float | None


def outcome_difference(passenger: MatchedPassenger) -> float | None:
    """D in seconds, or None when either run has no departure for them."""
    held, baseline = passenger.selected_strategy, passenger.without_holding
    # Absent from a run, or still waiting at its end: there is no Y to compare
    if held is None or baseline is None:
        return None
    if held.departure_s is None or baseline.departure_s is None:
        return None
    return held.departure_s - baseline.departure_s


def classify(difference_s: float) -> Group:
    """Put one D in a group; exactly the threshold still counts as unaffected."""
    if difference_s < -UNAFFECTED_THRESHOLD_S:
        return "better_off"
    if difference_s > UNAFFECTED_THRESHOLD_S:
        return "worse_off"
    return "unaffected"


def split_passengers(matched: Sequence[MatchedPassenger]) -> PassengerSplit:
    """Count each group and total and average the time saved and lost."""
    differences = [outcome_difference(passenger) for passenger in matched]
    known = [d for d in differences if d is not None]
    # Saved time is stored positive, so totals and averages read as gains
    saved = [-d for d in known if classify(d) == "better_off"]
    lost = [d for d in known if classify(d) == "worse_off"]
    return PassengerSplit(
        better_off=len(saved),
        worse_off=len(lost),
        unaffected=len(known) - len(saved) - len(lost),
        not_compared=len(differences) - len(known),
        total_time_saved_s=math.fsum(saved),
        total_time_lost_s=math.fsum(lost),
        average_time_saved_s=fmean(saved) if saved else None,
        average_time_lost_s=fmean(lost) if lost else None,
    )
