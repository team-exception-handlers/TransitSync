# AI contribution: 50% or more AI-generated
"""The web sliders use the same ranges as ``PARAMETER_RANGES`` (#256, #258).

The controls in web/src/lib/run-settings.ts copy the backend's ranges so they
never offer a value the API answers with 422. This reads that file and fails
when a number drifts.
"""

import re
from pathlib import Path

import pytest

from simulator.scenario_parameters import PARAMETER_RANGES

WEB_RANGE_NAMES = {
    "transfer_volume": "TRANSFER_VOLUME_RANGE",
    "train_headway_s": "TRAIN_HEADWAY_RANGE",
    "onboard_load": "ONBOARD_LOAD_RANGE",
    "walking_mean_s": "WALKING_TIME_RANGE",
    "max_hold_time": "MAX_HOLD_RANGE",
}


@pytest.mark.parametrize(("name", "constant"), sorted(WEB_RANGE_NAMES.items()))
def test_web_controls_use_the_same_ranges(name, constant):
    """The sliders copy PARAMETER_RANGES; a drift would let them send a 422."""
    source = (
        Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "run-settings.ts"
    ).read_text(encoding="utf-8")
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
