# AI contribution: 50% or more AI-generated
"""Number checks shared by the break-even calculation (US-2.2, #41, #42).

The walking-time CDFs, expected arrivals and the break-even function all take
seconds, passenger counts and weights. An invalid value would still give a
number that looks reasonable, so each input is checked once, here, and the
error names the field.
"""

import math


def finite_number(label: str, value: object, minimum: float | None = None) -> float:
    """Return ``value`` as a float after checking it is a usable number.

    Args:
        label: field name used in the error message.
        value: the value to check; ``int`` and ``float`` are accepted.
        minimum: smallest allowed value, inclusive, or ``None`` for no bound.

    Raises:
        ValueError: ``value`` is not a number, is NaN or infinite, or is below
            ``minimum``.
    """
    # bool is a subclass of int, so it is excluded explicitly
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be a number")
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite, got {value}")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be >= {minimum}, got {value}")
    return float(value)
