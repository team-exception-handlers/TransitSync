# AI contribution: 50% or more AI-generated
"""Walking-time CDFs F used by the decision engine (US-2.2, Task 2.2.1, #41).

F(t) is the share of a transfer group that has finished walking t seconds
after its feeder train arrived (Mathematical Foundations section 2). The
expected-arrivals calculation only needs F, never a random draw, so these
classes hold no generator and are deterministic.

Design pattern: Strategy. ``WalkingCdf`` is the interface and each family is
one interchangeable implementation:

- ``ShiftedExponentialCdf`` matches what ``WalkingTimeSampler`` draws today,
  so the controller believes the same walk the simulator produces
- ``LognormalCdf`` is the family the wiki fits to the field data (section 3);
  swapping to it is a configuration change, not a code change

Both use closed forms from ``math``, so no extra library is needed.
"""

import math
from dataclasses import dataclass
from typing import Protocol

from simulator.control.validation import finite_number


class WalkingCdf(Protocol):
    """Cumulative distribution of walking time, measured from feeder arrival."""

    def cdf(self, t_s: float) -> float:
        """Return the share of the group done walking ``t_s`` seconds in, 0 to 1."""
        ...


@dataclass(frozen=True, slots=True)
class ShiftedExponentialCdf:
    """F(t) = 1 - exp(-(t - min_s) / (mean_s - min_s)) for t >= min_s, else 0.

    Same parameters as ``TransferRoute.walking_mean_s`` and ``walking_min_s``.
    Raises ``ValueError`` unless 0 <= ``min_s`` < ``mean_s``.
    """

    mean_s: float
    min_s: float

    def __post_init__(self) -> None:
        min_s = finite_number("ShiftedExponentialCdf.min_s", self.min_s, 0.0)
        mean_s = finite_number("ShiftedExponentialCdf.mean_s", self.mean_s)
        if mean_s <= min_s:
            raise ValueError("ShiftedExponentialCdf.mean_s must exceed min_s")

    def cdf(self, t_s: float) -> float:
        """Return F(``t_s``); nobody finishes faster than ``min_s``."""
        if t_s <= self.min_s:
            return 0.0
        # expm1 keeps precision for t just above min_s, where exp(-x) is near 1
        return -math.expm1(-(t_s - self.min_s) / (self.mean_s - self.min_s))


@dataclass(frozen=True, slots=True)
class LognormalCdf:
    """F(t) = Phi((ln t - mu) / sigma) for t > 0, else 0.

    ``mu`` and ``sigma`` are the mean and spread of ln(walking time), so the
    median walk is exp(``mu``) seconds. Raises ``ValueError`` unless
    ``sigma`` > 0.
    """

    mu: float
    sigma: float

    def __post_init__(self) -> None:
        finite_number("LognormalCdf.mu", self.mu)
        if finite_number("LognormalCdf.sigma", self.sigma) <= 0:
            raise ValueError("LognormalCdf.sigma must be > 0")

    def cdf(self, t_s: float) -> float:
        """Return F(``t_s``); a walk cannot take zero or negative time."""
        if t_s <= 0:
            return 0.0
        # Phi(z) = erfc(-z / sqrt 2) / 2; erfc stays accurate deep in the left
        # tail, where 1 + erf(z) would lose every digit to cancellation
        z = (math.log(t_s) - self.mu) / self.sigma
        return 0.5 * math.erfc(-z / math.sqrt(2.0))
