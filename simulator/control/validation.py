# AI contribution: 50% or more AI-generated
"""Number checks shared by the break-even calculation (US-2.2, #41, #42).

The walking-time CDFs, expected arrivals and the break-even function all take
seconds, passenger counts and weights. An invalid value would still give a
number that looks reasonable, so each input is checked once, here, and the
error names the field.
"""

import math
import numbers
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
    # bool is registered as numbers.Real, so it is excluded explicitly;
    # np.bool_ is not registered, so it already fails the second check
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{label} must be a number")
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite, got {value}")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be >= {minimum}, got {value}")
    return float(value)


class PostRunValidationFailedError(ValueError):
    """Raised when a post-run rule check or passenger conservation invariant fails."""


def validate_run_results(run_output: Any) -> None:
    """Check cumulative constraints and passenger conservation
    across completed run results.

    Accepts a RunSummary, RunResult, or any metrics container object.
    Raises PostRunValidationFailedError if any violation or
    conservation error is detected.
    """
    # Fallback to check if metrics are nested or flat on the object
    metrics = getattr(run_output, "metrics", run_output)

    # Check passenger conservation (generated vs arrived/completed)
    generated = getattr(
        metrics, "passengers_generated", getattr(metrics, "generated", 0)
    )
    arrived = getattr(metrics, "passengers_arrived", getattr(metrics, "arrived", 0))

    if arrived > generated:
        raise PostRunValidationFailedError(
            f"Passenger conservation violation: arrived passengers ({arrived}) "
            f"exceed generated passengers ({generated})."
        )

    # Check for any recorded rule violations
    violations = getattr(
        run_output, "rule_violations", getattr(metrics, "rule_violations", [])
    )
    if violations:
        raise PostRunValidationFailedError(
            f"Run failed due to recorded operating rule violations: {violations}"
        )
