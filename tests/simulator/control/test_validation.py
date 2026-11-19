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
