# AI contribution: 50% or more AI-generated
"""Named, reusable disruption configurations for US-1.5 #29."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from simulator.trains.disruption import DelayInjection
from simulator.trains.suspension import LineSuspension


@dataclass(frozen=True, slots=True)
class DisruptionPreset:
    """A named disruption setup and the behaviour it is intended to test."""

    name: str
    description: str
    delay_injections: tuple[DelayInjection, ...] = ()
    line_suspensions: tuple[LineSuspension, ...] = ()
    spacing_irregularity_level: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Preset name cannot be empty")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Preset description cannot be empty")
        if any(not isinstance(item, DelayInjection) for item in self.delay_injections):
            raise ValueError(
                "Preset delay_injections must contain DelayInjection values"
            )
        if any(not isinstance(item, LineSuspension) for item in self.line_suspensions):
            raise ValueError(
                "Preset line_suspensions must contain LineSuspension values"
            )
        level = self.spacing_irregularity_level
        if level is not None and (
            isinstance(level, bool)
            or not isinstance(level, int | float)
            or not math.isfinite(level)
            or level < 0
        ):
            raise ValueError(
                "Preset spacing_irregularity_level must be finite and non-negative"
            )


_PRESETS = {
    "mcgill_platform_delay": DisruptionPreset(
        name="mcgill_platform_delay",
        description=(
            "Delay the REM train by 60 seconds at McGill to test delay propagation "
            "and its effect on a transfer."
        ),
        delay_injections=(
            DelayInjection(
                disruption_id="mcgill-rem-delay",
                time_s=120,
                delay_s=60,
                station_id="mcgill",
                platform_id="STA_ZCD_BT_QUAI_01_MCG",
            ),
        ),
    ),
    "green_line_suspension": DisruptionPreset(
        name="green_line_suspension",
        description=(
            "Suspend Green line dispatch from 100 to 200 seconds to test "
            "dispatch recovery and accumulated platform demand."
        ),
        line_suspensions=(LineSuspension("green", 100, 200),),
    ),
    "uneven_headways": DisruptionPreset(
        name="uneven_headways",
        description=(
            "Perturb Green line headways with coefficient of variation 0.3 to "
            "test irregular spacing while preserving seeded reproducibility."
        ),
        spacing_irregularity_level=0.3,
    ),
}

DISRUPTION_PRESETS: Mapping[str, DisruptionPreset] = MappingProxyType(_PRESETS)


def get_disruption_preset(name: str) -> DisruptionPreset:
    """Load a named preset, raising ``KeyError`` for an unknown name."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Preset name cannot be empty")
    try:
        return DISRUPTION_PRESETS[name]
    except KeyError as error:
        raise KeyError(f"Unknown disruption preset: {name}") from error
