# AI contribution: 50% or more AI-generated
"""Passengers helped or harmed by holding, from matched paired outcomes (#284).

For each passenger D = Y_hold - Y_no_hold (Mathematical Foundations section 9),
where Y is when they left the interchange on their connecting train. Negative
D means holding got them out sooner. Changes within the threshold are noise.
Someone still waiting when one run ends leaves after it there, so the run end
stands in for that Y and their D is a lower bound on the real change.
"""

import math
from collections.abc import Sequence
from statistics import fmean
from typing import Literal

from pydantic import BaseModel, Field

from api.passenger_outcomes import MatchedPassenger

# A change of 30 s or less counts as unaffected. Assumed until the team
# confirms it (US-6.3); its label and source are in parameter_provenance.json
UNAFFECTED_THRESHOLD_S = 30.0

Group = Literal["better_off", "worse_off", "unaffected"]


class PassengerSplit(BaseModel):
    """Group counts and the time each changed group gained or lost, in seconds."""

    better_off: int
    worse_off: int
    unaffected: int
    not_compared: int = Field(
        description="Passengers missing from a run or who left in neither, so D "
        "is unknown"
    )
    left_in_one_run: int = Field(
        description="Passengers who left in one run only; they are in a group "
        "above, with the run end as their other departure"
    )
    total_time_saved_s: float
    total_time_lost_s: float
    average_time_saved_s: float | None
    average_time_lost_s: float | None


def outcome_difference(passenger: MatchedPassenger, run_end_s: float) -> float | None:
    """D in seconds, or None when they are missing from a run or left in neither."""
    held, baseline = passenger.selected_strategy, passenger.without_holding
    if held is None or baseline is None:
        return None
    if held.departure_s is None and baseline.departure_s is None:
        return None
    # Still waiting at one run's end: they leave after run_end_s in that run,
    # so using it understates how much they gained or lost, never overstates
    held_s = run_end_s if held.departure_s is None else held.departure_s
    baseline_s = run_end_s if baseline.departure_s is None else baseline.departure_s
    return held_s - baseline_s


def classify(difference_s: float) -> Group:
    """Put one D in a group; exactly the threshold still counts as unaffected."""
    if difference_s < -UNAFFECTED_THRESHOLD_S:
        return "better_off"
    if difference_s > UNAFFECTED_THRESHOLD_S:
        return "worse_off"
    return "unaffected"


def _left_in_one_run(passenger: MatchedPassenger) -> bool:
    """True when exactly one run has a departure for this passenger."""
    held, baseline = passenger.selected_strategy, passenger.without_holding
    if held is None or baseline is None:
        return False
    return (held.departure_s is None) != (baseline.departure_s is None)


def split_passengers(
    matched: Sequence[MatchedPassenger], run_end_s: float
) -> PassengerSplit:
    """Count each group and total and average the time saved and lost.

    ``run_end_s`` is when both runs stop, in seconds from their start.
    """
    differences = [outcome_difference(passenger, run_end_s) for passenger in matched]
    known = [d for d in differences if d is not None]
    # Saved time is stored positive, so totals and averages read as gains
    saved = [-d for d in known if classify(d) == "better_off"]
    lost = [d for d in known if classify(d) == "worse_off"]
    return PassengerSplit(
        better_off=len(saved),
        worse_off=len(lost),
        unaffected=len(known) - len(saved) - len(lost),
        not_compared=len(differences) - len(known),
        left_in_one_run=sum(_left_in_one_run(passenger) for passenger in matched),
        total_time_saved_s=math.fsum(saved),
        total_time_lost_s=math.fsum(lost),
        average_time_saved_s=fmean(saved) if saved else None,
        average_time_lost_s=fmean(lost) if lost else None,
    )
