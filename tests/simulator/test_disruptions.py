# AI contribution: 50% or more AI-generated
"""Named disruption preset tests for US-1.5 #29."""

import pytest

from simulator.disruptions import DISRUPTION_PRESETS, get_disruption_preset


def test_presets_cover_distinct_disruption_types_and_explain_their_purpose():
    assert set(DISRUPTION_PRESETS) == {
        "mcgill_platform_delay",
        "green_line_suspension",
        "uneven_headways",
    }
    assert all(preset.description.strip() for preset in DISRUPTION_PRESETS.values())
    assert (
        len(
            {
                (
                    bool(preset.delay_injections),
                    bool(preset.line_suspensions),
                    preset.spacing_irregularity_level is not None,
                )
                for preset in DISRUPTION_PRESETS.values()
            }
        )
        == 3
    )


def test_named_delay_preset_has_a_complete_location_and_time_configuration():
    preset = get_disruption_preset("mcgill_platform_delay")
    delay = preset.delay_injections[0]
    assert (delay.time_s, delay.delay_s) == (120, 60)
    assert (delay.station_id, delay.platform_id, delay.train_id) == (
        "mcgill",
        "rem_mcgill_0",
        None,
    )


def test_unknown_preset_name_is_reported():
    with pytest.raises(KeyError, match="Unknown disruption preset"):
        get_disruption_preset("not-a-preset")
