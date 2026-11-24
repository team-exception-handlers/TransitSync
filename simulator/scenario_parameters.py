# AI contribution: 50% or more AI-generated
"""Demand and service parameters a user can change for a run (US-5.1, #258).

They live in the scenario's optional ``"parameters"`` object, so a scenario
file, a time-of-day preset and the run endpoint set them the same way.

- **Transfer volume** (M, Mathematical Foundations section 2): passengers
  leaving each REM train to transfer, a group per train, not a rate
- **Train frequency**: the headway in seconds between connecting metro
  trains. ``None`` keeps the GTFS timetable
- **Onboard load** (L in the break-even cost): passengers already on board
- **Walking time**: mean transfer walk in seconds, above ``WALKING_MIN_S``

Maximum hold already lives in ``operating_rules.max_hold_time`` (US-2.4), so
only its range is listed here, in the one table every control reads.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# The fastest observed walk, in seconds. Fixed, not a user parameter: it is
# the floor of the walking-time distribution, not a demand assumption.
WALKING_MIN_S = 30.0

PARAMETER_FIELDS = frozenset(
    {"transfer_volume", "train_headway_s", "onboard_load", "walking_mean_s"}
)


@dataclass(frozen=True, slots=True)
class ParameterRange:
    """Inclusive bounds and step of one parameter, in that parameter's unit."""

    minimum: float
    maximum: float
    step: float

    def contains(self, value: float) -> bool:
        """True inside the bounds and on a whole step, allowing float rounding."""
        if not self.minimum <= value <= self.maximum:
            return False
        steps = (value - self.minimum) / self.step
        return math.isclose(steps, round(steps), abs_tol=1e-9)


# Lookup table of valid ranges, the single source of truth for the scenario
# loader and the API request model. The web controls copy these numbers;
# tests/simulator/test_scenario_parameters.py fails if they drift.
PARAMETER_RANGES: Mapping[str, ParameterRange] = {
    # The wiki sweeps 40, 60 and 80; 0 runs with no transfers at all.
    "transfer_volume": ParameterRange(0, 200, 1),
    # Below 120 s trains would crowd the 60 s minimum gap once dwells are added.
    "train_headway_s": ParameterRange(120, 600, 30),
    # Up to the 800-passenger train capacity used by the run endpoint.
    "onboard_load": ParameterRange(0, 800, 10),
    # The mean must stay above WALKING_MIN_S, so the range starts above it.
    "walking_mean_s": ParameterRange(45, 600, 5),
    # Same limits as SimulationRunRequest.max_hold_time (US-2.4).
    "max_hold_time": ParameterRange(5, 300, 5),
}


class ScenarioParametersError(ValueError):
    """A ``parameters`` value is invalid; the message starts with its path."""


@dataclass(frozen=True, slots=True)
class ScenarioParameters:
    """Validated demand and service values for one run.

    Defaults are the values the run endpoint used before #258, except transfer
    volume, which is now a group size per train (60, the middle of the wiki's
    sweep) instead of a Low, Normal or High label.
    """

    transfer_volume: int = 60
    train_headway_s: float | None = None
    onboard_load: int = 300
    walking_mean_s: float = 120.0

    def to_dict(self) -> dict[str, Any]:
        """Return the parameters as saved in a scenario file and manifest."""
        return {
            "transfer_volume": self.transfer_volume,
            "train_headway_s": self.train_headway_s,
            "onboard_load": self.onboard_load,
            "walking_mean_s": self.walking_mean_s,
        }


def parse_scenario_parameters(value: object) -> ScenarioParameters:
    """Validate the ``parameters`` object of a scenario.

    A missing object gives the defaults. Fields are checked in a fixed order,
    so the first bad one is reported, and every message names its field, for
    example ``parameters.onboard_load: must be between 0 and 800``. Raises
    ``ScenarioParametersError``.
    """
    if value is None:
        return ScenarioParameters()
    if not isinstance(value, Mapping):
        raise ScenarioParametersError("parameters: must be an object")
    unknown = sorted(value.keys() - PARAMETER_FIELDS)
    if unknown:
        raise ScenarioParametersError(f"parameters.{unknown[0]}: unknown field")
    kwargs: dict[str, Any] = {}
    for name in ("transfer_volume", "onboard_load"):
        if name in value:
            kwargs[name] = int(_checked_number(value[name], name, whole=True))
    if "walking_mean_s" in value:
        walking = value["walking_mean_s"]
        kwargs["walking_mean_s"] = _checked_number(walking, "walking_mean_s")
    # None is a real choice here: it means "follow the GTFS timetable".
    headway = value.get("train_headway_s")
    if headway is not None:
        kwargs["train_headway_s"] = _checked_number(headway, "train_headway_s")
    return ScenarioParameters(**kwargs)


def _checked_number(value: object, name: str, *, whole: bool = False) -> float:
    """Return ``value`` as a float after the type, range and step checks.

    ``bool`` is rejected explicitly because it is a subclass of ``int``. A
    whole-number field also rejects floats such as 60.5.
    """
    path = f"parameters.{name}"
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ScenarioParametersError(f"{path}: expected a number")
    if not math.isfinite(value):
        raise ScenarioParametersError(f"{path}: must be finite")
    if whole and not float(value).is_integer():
        raise ScenarioParametersError(f"{path}: expected a whole number")
    bounds = PARAMETER_RANGES[name]
    if not bounds.contains(float(value)):
        raise ScenarioParametersError(
            f"{path}: must be between {bounds.minimum:g} and {bounds.maximum:g} "
            f"in steps of {bounds.step:g}"
        )
    return float(value)
