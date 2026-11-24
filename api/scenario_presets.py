# AI contribution: 50% or more AI-generated
"""List the time-of-day presets for the Scenario setup view (#261, #262).

``GET /scenario/presets`` returns every preset in ``PRESET_SETTINGS`` with
its label, time window and the conditions it runs with, so the front end
shows only presets the run endpoint accepts and never keeps its own copy of
their values. Defaults are filled in, so each preset lists all five values.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from simulator.scenario import PRESET_SETTINGS
from simulator.scenario_parameters import parse_scenario_parameters


class PresetConditions(BaseModel):
    """The five run values of one preset; a None headway is the timetable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    transfer_volume: int = Field(ge=0)
    train_headway_s: float | None = Field(default=None, gt=0)
    onboard_load: int = Field(ge=0)
    walking_mean_s: float = Field(gt=0)
    max_hold_time: float = Field(gt=0)


class ScenarioPreset(BaseModel):
    """One selectable time-of-day preset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    # Local clock time the window starts, "HH:MM:SS", and its length in seconds
    start_time: str = Field(min_length=5)
    duration_s: float = Field(gt=0)
    conditions: PresetConditions


def list_presets() -> list[ScenarioPreset]:
    """Return the presets in definition order with every value filled in.

    Parameter values go through ``parse_scenario_parameters``, the scenario
    loader's own check, so a bad preset fails here with its field name
    instead of reaching the page. Raises ``ScenarioParametersError``.
    """
    presets = []
    for name, preset in PRESET_SETTINGS.items():
        parameters = parse_scenario_parameters(preset["parameters"])
        presets.append(
            ScenarioPreset(
                name=name,
                label=preset["label"],
                start_time=preset["start_time"],
                duration_s=preset["duration_s"],
                conditions=PresetConditions(
                    **parameters.to_dict(),
                    max_hold_time=preset["max_hold_time"],
                ),
            )
        )
    return presets
