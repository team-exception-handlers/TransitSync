# AI contribution: 50% or more AI-generated
"""Unit tests for the station-view adapter's mode-switch records (#60).

Records are hand-built in the shape written by
``DecisionAuditLog.record_mode_switch``, so the filter can be checked without
running a simulation.
"""

import pytest

from api.station_view import ModeSwitchResponse, _mode_switch_records
from simulator.control.decision_audit import KIND_HOLD_SEARCH, KIND_MODE_SWITCH

SHOWN = {"rem_mcgill_0", "green_mcgill_0"}


def _switch(time_s: float, platform_id: str, to_mode: str) -> dict[str, object]:
    """Return one audit record of kind ``mode_switch``, with audit-only keys."""
    from_mode = (
        "connection_protection"
        if to_mode == "headway_regulation"
        else "headway_regulation"
    )
    return {
        "schema_version": 2,
        "kind": KIND_MODE_SWITCH,
        "strategy": "adaptive",
        "time_s": time_s,
        "train_id": "T1",
        "station_id": "32",
        "platform_id": platform_id,
        "line_id": "1",
        "from_mode": from_mode,
        "to_mode": to_mode,
        "service_irregularity": 0.4,
        "irregularity_threshold": 0.25,
    }


def test_keeps_only_switches_on_the_shown_platforms_in_time_order() -> None:
    """Other interchanges and other audit kinds are dropped; times are sorted."""
    records = [
        _switch(900.0, "green_mcgill_0", "connection_protection"),
        _switch(300.0, "orange_gare_centrale_bonaventure_0", "headway_regulation"),
        {"kind": KIND_HOLD_SEARCH, "time_s": 100.0, "platform_id": "green_mcgill_0"},
        _switch(420.0, "rem_mcgill_0", "headway_regulation"),
    ]

    switches = _mode_switch_records(records, SHOWN)

    assert [switch["time_s"] for switch in switches] == [420.0, 900.0]
    assert [switch["platform_id"] for switch in switches] == [
        "rem_mcgill_0",
        "green_mcgill_0",
    ]


def test_drops_audit_only_keys_so_the_strict_model_accepts_the_record() -> None:
    """``kind``, ``strategy`` and ``schema_version`` are not response fields."""
    (switch,) = _mode_switch_records(
        [_switch(420.0, "rem_mcgill_0", "headway_regulation")], SHOWN
    )

    model = ModeSwitchResponse.model_validate(switch)

    assert "kind" not in switch
    assert model.to_mode == "headway_regulation"


def test_returns_no_switches_without_adaptive_records() -> None:
    """Non-adaptive runs have no mode-switch records, so the list is empty."""
    hold = {"kind": KIND_HOLD_SEARCH, "time_s": 60.0, "platform_id": "rem_mcgill_0"}

    assert _mode_switch_records([hold], SHOWN) == []


@pytest.mark.parametrize("mode", ["rolling_horizon", "no_control"])
def test_model_rejects_a_mode_adaptive_cannot_switch_to(mode: str) -> None:
    """Adaptive only alternates between its two delegate strategies."""
    record = {
        **_mode_switch_records(
            [_switch(420.0, "rem_mcgill_0", "headway_regulation")], SHOWN
        )[0],
        "to_mode": mode,
    }

    with pytest.raises(ValueError, match="to_mode"):
        ModeSwitchResponse.model_validate(record)
