# AI contribution: 50% or more AI-generated
"""Number checks shared by the calculation and runtime verification

(US-2.2, US-2.5, #41, #42, #195).

The walking-time CDFs, expected arrivals, break-even function, and post-run
event-log verification all take seconds, passenger counts, and weights.
"""

from __future__ import annotations

import json
import math
import numbers
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


def finite_number(label: str, value: object, minimum: float | None = None) -> float:
    """Return ``value`` as a float after checking it is a usable number.

    Args:
        label: field name used in the error message.
        value: the value to check. Any real number is accepted, including
            numpy scalars such as the candidate holds from ``np.arange``.
        minimum: smallest allowed value, inclusive, or ``None`` for no bound.

    Raises:
        ValueError: ``value`` is not a number, is NaN or infinite, or is below
            ``minimum``.
    """
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{label} must be a number")
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite, got {value}")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be >= {minimum}, got {value}")
    return float(value)


class PostRunValidationFailedError(ValueError):
    """Raised when a post-run rule check or invariant fails."""


@dataclass(frozen=True)
class RuleViolation:
    """One place where a finished run broke an operating rule.

    ``rule`` uses the rule names of ``OperatingRulesConfig.rule_action_map``.
    ``subject_id`` is the held train for a hold, or the platform for a gap.
    """

    rule: Literal["max_hold_exceeded", "headway_violation"]
    time_s: float
    subject_id: str
    message: str


def _hold_violation(
    event: Mapping[str, Any], max_hold_s: float
) -> RuleViolation | None:
    """A hold whose applied length is over the maximum, else None."""
    applied_s = event.get("applied_s", 0.0)
    if applied_s <= max_hold_s:
        return None
    train_id, time_s = str(event.get("train_id")), event.get("time_s", 0.0)
    return RuleViolation(
        "max_hold_exceeded",
        time_s,
        train_id,
        f"Max Hold Violation: Train {train_id} at t={time_s}s "
        f"applied hold of {applied_s}s exceeds max {max_hold_s}s.",
    )


def _gap_violation(
    event: Mapping[str, Any], last_departure: dict[str, float], min_safe_gap_s: float
) -> RuleViolation | None:
    """A departure too soon after the previous one at its platform, else None.

    Updates ``last_departure`` so the next departure is compared with this one.
    """
    platform_id = event.get("platform_id") or event.get("station_id")
    if not platform_id:
        return None
    time_s = event.get("time_s", 0.0)
    previous_s = last_departure.get(platform_id)
    last_departure[platform_id] = time_s
    if previous_s is None or time_s - previous_s >= min_safe_gap_s:
        return None
    return RuleViolation(
        "headway_violation",
        time_s,
        str(platform_id),
        f"Min Safe Gap Violation: Platform {platform_id} "
        f"gap {time_s - previous_s:.1f}s < minimum {min_safe_gap_s}s.",
    )


def find_rule_violations(
    events: Iterable[Mapping[str, Any]], max_hold_s: float, min_safe_gap_s: float
) -> list[RuleViolation]:
    """Return every max hold and minimum safe gap violation in time order.

    ``events`` are event-log records in log order. The API returns the result
    with each run, and the post-run check below raises on it.
    """
    violations: list[RuleViolation] = []
    last_departure: dict[str, float] = {}
    for event in events:
        event_type = event.get("event_type")
        found = None
        if event_type == "hold":
            found = _hold_violation(event, max_hold_s)
        elif event_type == "train_departure":
            found = _gap_violation(event, last_departure, min_safe_gap_s)
        if found is not None:
            violations.append(found)
    return violations


def _verify_event_log_rules(
    events_path: Path, max_hold_s: float, min_safe_gap_s: float
) -> None:
    """Verify max hold and minimum safe gap from events.jsonl."""
    with open(events_path, encoding="utf-8") as f:
        events = [json.loads(line) for line in f if line.strip()]
    violations = find_rule_violations(events, max_hold_s, min_safe_gap_s)
    if violations:
        msg = "Post-run verification failed with violation(s):\n" + "\n".join(
            f" - {v.message}" for v in violations
        )
        raise PostRunValidationFailedError(msg)


def validate_run_results(
    run_output: Any,
    max_hold_s: float = 300.0,
    min_safe_gap_s: float = 60.0,
) -> None:
    """Read events.jsonl and check operating rules and passenger conservation."""
    metrics = getattr(run_output, "metrics", run_output)
    violations = getattr(
        run_output, "rule_violations", getattr(metrics, "rule_violations", [])
    )
    if violations:
        raise PostRunValidationFailedError(
            f"Run failed due to recorded operating rule violations: {violations}"
        )

    events_path = getattr(run_output, "events_path", None)
    if events_path and Path(events_path).exists():
        _verify_event_log_rules(Path(events_path), max_hold_s, min_safe_gap_s)

    has_gen = metrics and (
        hasattr(metrics, "passengers_generated") or hasattr(metrics, "generated")
    )
    if metrics and has_gen:
        generated = getattr(
            metrics, "passengers_generated", getattr(metrics, "generated", 0)
        )
        arrived = getattr(metrics, "passengers_arrived", getattr(metrics, "arrived", 0))

        if arrived > generated:
            raise PostRunValidationFailedError(
                f"Passenger conservation violation: arrived ({arrived}) "
                f"exceed generated ({generated})."
            )
