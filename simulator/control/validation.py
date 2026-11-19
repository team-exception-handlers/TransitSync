"""Number checks shared by the calculation and runtime verification

(US-2.2, US-2.5, #41, #42, #195).

The walking-time CDFs, expected arrivals, break-even function, and post-run
event-log verification all take seconds, passenger counts, and weights.
"""

from __future__ import annotations

import json
import math
import numbers
from pathlib import Path
from typing import Any


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


def _verify_event_log_rules(
    events_path: Path, max_hold_s: float, min_safe_gap_s: float
) -> None:
    """Verify max hold and minimum safe gap from events.jsonl."""
    events = []
    with open(events_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    violations: list[str] = []
    platform_last_departure: dict[str, float] = {}

    for event in events:
        event_type = event.get("event_type")

        if event_type == "hold":
            applied_s = event.get("applied_s", 0.0)
            train_id = event.get("train_id")
            timestamp = event.get("time_s", 0.0)

            if applied_s > max_hold_s:
                violations.append(
                    f"Max Hold Violation: Train {train_id} at t={timestamp}s "
                    f"applied hold of {applied_s}s exceeds max {max_hold_s}s."
                )

        elif event_type == "train_departure":
            platform_id = event.get("platform_id") or event.get("station_id")
            timestamp = event.get("time_s", 0.0)

            if platform_id:
                if platform_id in platform_last_departure:
                    gap = timestamp - platform_last_departure[platform_id]
                    if gap < min_safe_gap_s:
                        violations.append(
                            f"Min Safe Gap Violation: Platform {platform_id} "
                            f"gap {gap:.1f}s < minimum {min_safe_gap_s}s."
                        )
                platform_last_departure[platform_id] = timestamp

    if violations:
        msg = "Post-run verification failed with violation(s):\n" + "\n".join(
            f" - {v}" for v in violations
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
