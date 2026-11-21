# AI contribution: 50% or more AI-generated
"""Unit tests for the station-view adapter's audit-derived records.

Mode switches (#60) and decision estimates (#39) are hand-built in the shape
written by ``DecisionAuditLog``, so the filters can be checked without running
a simulation.
"""

import pytest

from api.station_view import (
    EstimatesResponse,
    ModeSwitchResponse,
    _estimate_records,
    _mode_switch_records,
    _rule_check,
    _time_series_records,
)
from simulator.control.decision_audit import (
    KIND_ESTIMATES,
    KIND_HOLD_SEARCH,
    KIND_MODE_SWITCH,
)
from simulator.control.settings import OperatingRulesConfig

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


def _estimates(time_s: float, train_id: str, platform_id: str) -> dict[str, object]:
    """Return one audit record of kind ``estimates`` naming three trains."""
    return {
        "schema_version": 2,
        "kind": KIND_ESTIMATES,
        "time_s": time_s,
        "train_id": train_id,
        "station_id": "32",
        "platform_id": platform_id,
        "trains": [
            {
                "train_id": other,
                "predicted_arrival_s": {"seen": 181.0, "true": 165.0},
                "onboard_load": {"seen": 249, "true": 394},
            }
            for other in ("T0", train_id, "T9")
        ],
        "transfers": [
            {
                "group_id": "G1",
                "passenger_count": {"seen": 38.0, "true": 42.0},
                "group_size": {"seen": 54.0, "true": 60.0},
            }
        ],
    }


def _decision(time_s: float, train_id: str, platform_id: str) -> dict[str, object]:
    """Return a shown decision with only the fields used for matching."""
    return {"time_s": time_s, "train_id": train_id, "platform_id": platform_id}


def test_estimates_are_kept_only_for_shown_decisions_and_cut_to_the_held_train():
    """One record per shown decision; other trains are dropped.

    The held train is at the platform, so its arrival is cleared while its
    seen and true load stay. Transfer groups are kept unchanged.
    """
    records = [
        _estimates(120.0, "T1", "green_mcgill_0"),
        _estimates(240.0, "T2", "green_mcgill_0"),  # no decision at 240 s
        _estimates(120.0, "T1", "green_mcgill_1"),  # same time, other platform
        {"kind": KIND_HOLD_SEARCH, "time_s": 120.0, "train_id": "T1"},
    ]

    (kept,) = _estimate_records(records, [_decision(120.0, "T1", "green_mcgill_0")])

    assert [train["train_id"] for train in kept["trains"]] == ["T1"]
    (held,) = kept["trains"]
    assert held["predicted_arrival_s"] == {"seen": None, "true": None}
    assert held["onboard_load"] == {"seen": 249, "true": 394}
    assert kept["transfers"][0]["passenger_count"] == {"seen": 38.0, "true": 42.0}
    assert "kind" not in kept
    assert EstimatesResponse.model_validate(kept).platform_id == "green_mcgill_0"


def test_no_decisions_means_no_estimates():
    """No control holds nobody, so even recorded estimates are not returned."""
    assert _estimate_records([_estimates(120.0, "T1", "green_mcgill_0")], []) == []


# A 150 s hold at t = 900 s, as a hold event appears in events.jsonl.
LONG_HOLD = {
    "event_type": "hold",
    "time_s": 900.0,
    "train_id": "T1",
    "applied_s": 150.0,
}


def test_rule_check_uses_the_run_maximum_hold_not_the_default() -> None:
    """A run limited to 120 s fails on a 150 s hold that 300 s would allow."""
    check = _rule_check([LONG_HOLD], OperatingRulesConfig(max_hold_time=120.0))

    assert check.passed is False
    (violation,) = check.violations
    assert violation.rule == "max_hold_exceeded"
    assert violation.subject_id == "T1"
    assert violation.time_s == pytest.approx(900.0)
    assert "exceeds max 120.0s" in violation.message


def test_rule_check_passes_a_run_within_its_limits() -> None:
    """The same hold is within the default 300 s maximum, so nothing is reported."""
    check = _rule_check([LONG_HOLD], OperatingRulesConfig())

    assert check.model_dump() == {"passed": True, "violations": []}


def test_time_series_assigns_wait_delay_and_holds_to_full_horizon() -> None:
    """A terminal event at 420 s belongs in bucket [300,600), with holds marked."""
    event_records = [
        {
            "event_type": "passenger_arrival",
            "passenger_id": "P1",
            "platform_id": "green_mcgill_0",
            "time_s": 360.0,
        },
        {
            "event_type": "boarding",
            "passenger_id": "P1",
            "platform_id": "green_mcgill_0",
            "time_s": 420.0,
        },
        {
            "event_type": "hold",
            "train_id": "T1",
            "station_id": "32",
            "platform_id": "rem_mcgill_0",
            "time_s": 300.0,
            "applied_s": 45.0,
        },
    ]

    series = _time_series_records(event_records, [], 601.0, SHOWN)

    assert len(series["buckets"]) == 3
    assert series["buckets"][1]["average_passenger_delay_s"] == 60.0
    assert series["buckets"][1]["passenger_count"] == 1
    assert series["buckets"][2]["average_passenger_delay_s"] == 0.0
    assert [hold["time_s"] for hold in series["hold_events"]] == [300.0]
