# AI contribution: 50% or more AI-generated
"""Tests for post-run validation and passenger conservation checks
(US-2.5, Task 2.5.6, #59).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from simulator.control.validation import (
    PostRunValidationFailedError,
    RuleViolation,
    find_rule_violations,
    validate_run_results,
)


@dataclass
class MockMetrics:
    passengers_generated: int
    passengers_arrived: int


@dataclass
class MockRunResult:
    metrics: MockMetrics
    rule_violations: list = field(default_factory=list)
    events_path: Path | None = None


def test_valid_run_passes_validation():
    result = MockRunResult(
        metrics=MockMetrics(passengers_generated=100, passengers_arrived=95)
    )
    validate_run_results(result)  # Should not raise


def test_passenger_conservation_failure_raises_error():
    result = MockRunResult(
        metrics=MockMetrics(passengers_generated=100, passengers_arrived=105)
    )
    with pytest.raises(
        PostRunValidationFailedError, match="Passenger conservation violation"
    ):
        validate_run_results(result)


def test_recorded_rule_violations_raises_error():
    result = MockRunResult(
        metrics=MockMetrics(passengers_generated=100, passengers_arrived=90),
        rule_violations=["max_hold_exceeded"],
    )
    with pytest.raises(
        PostRunValidationFailedError, match="recorded operating rule violations"
    ):
        validate_run_results(result)


def test_departures_with_unsafe_gap_raise_error(tmp_path):
    """Two departures 10 seconds apart violate the 60-second minimum gap."""
    events_path = tmp_path / "events.jsonl"
    events = [
        {
            "event_type": "train_departure",
            "time_s": 100.0,
            "train_id": "A",
            "platform_id": "P1",
        },
        {
            "event_type": "train_departure",
            "time_s": 110.0,
            "train_id": "B",
            "platform_id": "P1",
        },
    ]

    events_path.write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )

    result = MockRunResult(
        metrics=MockMetrics(passengers_generated=100, passengers_arrived=95),
        events_path=events_path,
    )

    with pytest.raises(PostRunValidationFailedError, match="Min Safe Gap Violation"):
        validate_run_results(result)


def _hold(time_s: float, applied_s: float, train_id: str = "T1") -> dict:
    return {
        "event_type": "hold",
        "time_s": time_s,
        "train_id": train_id,
        "applied_s": applied_s,
    }


def _departure(time_s: float, platform_id: str) -> dict:
    return {
        "event_type": "train_departure",
        "time_s": time_s,
        "platform_id": platform_id,
    }


def test_find_rule_violations_returns_a_hold_over_the_maximum():
    """A 310 s hold against a 300 s maximum is one max-hold violation."""
    found = find_rule_violations([_hold(500.0, 310.0)], 300.0, 60.0)

    assert found == [
        RuleViolation(
            "max_hold_exceeded",
            500.0,
            "T1",
            "Max Hold Violation: Train T1 at t=500.0s "
            "applied hold of 310.0s exceeds max 300.0s.",
        )
    ]


def test_find_rule_violations_returns_a_short_gap_at_one_platform():
    """Departures at 100 s and 159 s leave a 59 s gap, under the 60 s minimum."""
    found = find_rule_violations(
        [_departure(100.0, "P1"), _departure(159.0, "P1")], 300.0, 60.0
    )

    assert found == [
        RuleViolation(
            "headway_violation",
            159.0,
            "P1",
            "Min Safe Gap Violation: Platform P1 gap 59.0s < minimum 60.0s.",
        )
    ]


@pytest.mark.parametrize(
    "events",
    [
        pytest.param([_hold(500.0, 300.0)], id="hold-exactly-at-max"),
        pytest.param(
            [_departure(100.0, "P1"), _departure(160.0, "P1")], id="gap-exactly-at-min"
        ),
        pytest.param(
            [_departure(100.0, "P1"), _departure(110.0, "P2")], id="different-platforms"
        ),
        pytest.param(
            [{"event_type": "train_arrival", "time_s": 5.0}], id="other-event-types"
        ),
        pytest.param([], id="empty-log"),
    ],
)
def test_find_rule_violations_passes_runs_within_the_limits(events):
    """Limits are inclusive, and only same-platform departures are compared."""
    assert find_rule_violations(events, 300.0, 60.0) == []


def test_find_rule_violations_keeps_log_order_across_rules():
    """Each departure is compared with the one just before it at that platform."""
    events = [
        _departure(100.0, "P1"),
        _hold(120.0, 400.0, "T2"),
        _departure(130.0, "P1"),
        _departure(150.0, "P1"),
    ]

    found = find_rule_violations(events, 300.0, 60.0)

    assert [(item.rule, item.time_s) for item in found] == [
        ("max_hold_exceeded", 120.0),
        ("headway_violation", 130.0),
        ("headway_violation", 150.0),
    ]
