# AI contribution: 50% or more AI-generated
"""Tests for post-run validation and passenger conservation checks
(US-2.5, Task 2.5.6, #59).
"""

from dataclasses import dataclass, field

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
