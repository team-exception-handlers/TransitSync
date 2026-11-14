# AI contribution: 50% or more AI-generated
"""US-2.3 #48: hold trains to keep a target gap between platform departures.

Uses the Strategy pattern and actual departure times; ignores transfers.
See Mathematical Foundations (Section 6) for train timing.
The simulator applies operating limits to the requested hold.
"""

import numbers
from collections.abc import Mapping
from dataclasses import dataclass
from sys import float_info
from types import MappingProxyType
from typing import ClassVar

from simulator.control.interface import (
    DecisionController,
    HoldAction,
    ObservationSnapshot,
    as_actions,
)


@dataclass(frozen=True)
class HeadwayRegulationStrategy(DecisionController):
    """Use a fixed positive, finite target gap in seconds for each platform.

    Copy and freeze ``target_headways_s`` so caller changes cannot affect it.
    Store Python numbers so settings can be saved as JSON.
    Raise ``ValueError`` for bad mappings, blank IDs or invalid target seconds.
    """

    target_headways_s: Mapping[str, float]
    name: ClassVar[str] = "headway_regulation"

    def __post_init__(self) -> None:
        """Check target seconds and store a copy that cannot be changed."""
        if not isinstance(self.target_headways_s, Mapping):
            raise ValueError("target_headways_s must be a mapping")
        targets = dict(self.target_headways_s)
        for platform_id, target_s in targets.items():
            if not isinstance(platform_id, str) or not platform_id.strip():
                raise ValueError("target platform ID must be a non-empty string")
            targets[platform_id] = _check_target(platform_id, target_s)
        # Copy first: a read-only view still follows changes to the original.
        object.__setattr__(self, "target_headways_s", MappingProxyType(targets))

    def evaluate(self, observation: ObservationSnapshot) -> tuple[HoldAction, ...]:
        """Request the seconds left to reach the target gap, or no action.

        Raise ``ValueError`` if the deciding platform or its target is missing,
        including before the first departure.
        """
        platform_id = observation.platform_id
        platform = next(
            (p for p in observation.platforms if p.platform_id == platform_id), None
        )
        if platform is None:
            raise ValueError(f"Missing deciding platform {platform_id!r}")
        if platform_id not in self.target_headways_s:
            raise ValueError(f"Missing target for platform {platform_id!r}")
        # A departure at zero is valid; None means no previous departure.
        if platform.last_departure_s is None:
            return as_actions(None)
        gap_s = observation.time_s - platform.last_departure_s
        hold_s = self.target_headways_s[platform_id] - gap_s
        # Only a gap shorter than the target needs a hold.
        hold = None
        if hold_s > 0:
            hold = HoldAction(observation.train_id, hold_s, self.name)
        return as_actions(hold)


def _check_target(platform_id: str, target_s: float) -> float:
    """Return positive finite seconds as a Python number, or raise ValueError."""
    message = f"Target for {platform_id!r} must be finite positive seconds"
    if isinstance(target_s, bool) or not isinstance(target_s, numbers.Real):
        raise ValueError(message)
    try:
        # Preserve integer precision while making NumPy values JSON-compatible.
        seconds = (
            int(target_s) if isinstance(target_s, numbers.Integral) else float(target_s)
        )
    except OverflowError as error:
        raise ValueError(message) from error
    if not 0 < seconds <= float_info.max:
        raise ValueError(message)
    return seconds
