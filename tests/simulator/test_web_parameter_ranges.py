# AI contribution: 50% or more AI-generated
"""The web sliders use the same ranges and defaults as the backend (#256, #258).

The controls in web/src/lib/run-settings.ts copy the backend's ranges so they
never offer a value the API answers with 422, and its defaults, because the UI
always sends them: a stale copy would quietly override a new backend default.
This reads that file and fails when a number drifts.
"""

import re
from pathlib import Path

import pytest

from simulator.control.settings import OperatingRulesConfig
from simulator.scenario_parameters import PARAMETER_RANGES, ScenarioParameters

WEB_RANGE_NAMES = {
    "transfer_volume": "TRANSFER_VOLUME_RANGE",
    "train_headway_s": "TRAIN_HEADWAY_RANGE",
    "onboard_load": "ONBOARD_LOAD_RANGE",
    "walking_mean_s": "WALKING_TIME_RANGE",
    "max_hold_time": "MAX_HOLD_RANGE",
}


RUN_SETTINGS_PATH = (
    Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "run-settings.ts"
)


def _default_run_settings() -> str:
    """Return the body of DEFAULT_RUN_SETTINGS in run-settings.ts."""
    source = RUN_SETTINGS_PATH.read_text(encoding="utf-8")
    found = re.search(r"DEFAULT_RUN_SETTINGS: RunSettings = \{(.*?)\n\};", source, re.S)
    assert found is not None, "DEFAULT_RUN_SETTINGS"
    return found.group(1)


def _backend_defaults() -> dict[str, str]:
    """The backend defaults as the TypeScript literal each one should be."""
    defaults = {
        **ScenarioParameters().to_dict(),
        "max_hold_time": OperatingRulesConfig().max_hold_time,
    }
    return {
        name: "null" if value is None else f"{float(value):g}"
        for name, value in defaults.items()
    }


@pytest.mark.parametrize(("name", "expected"), sorted(_backend_defaults().items()))
def test_web_defaults_match_the_backend(name, expected):
    """The UI sends its defaults on every run, so they must equal the backend's."""
    found = re.search(rf"^\s*{name}: ([^,]+),$", _default_run_settings(), re.M)
    assert found is not None, name
    assert found.group(1) == expected


@pytest.mark.parametrize(("name", "constant"), sorted(WEB_RANGE_NAMES.items()))
def test_web_controls_use_the_same_ranges(name, constant):
    """The sliders copy PARAMETER_RANGES; a drift would let them send a 422."""
    source = RUN_SETTINGS_PATH.read_text(encoding="utf-8")
    found = re.search(
        rf"{constant}: SettingRange = \{{ min: ([\d.]+), max: ([\d.]+), "
        rf"step: ([\d.]+) \}}",
        source,
    )
    assert found is not None, constant
    bounds = PARAMETER_RANGES[name]
    assert tuple(float(part) for part in found.groups()) == (
        bounds.minimum,
        bounds.maximum,
        bounds.step,
    )
