# AI contribution: 50% or more AI-generated
"""Configurable dispatch irregularity for US-1.5 #28, in seconds.

The level is the coefficient of variation (standard deviation / mean) of
each requested headway. Positive lognormal multipliers have mean 1 and
variance level**2. This distribution is a modelling choice: the issue and
Mathematical Foundations do not prescribe a spacing-noise distribution.
Minimum-gap constraints still apply independently in TrainComponent (§6).
"""

import math
from collections.abc import Sequence

import numpy as np


def perturb_dispatch_times(
    departure_times_s: Sequence[float],
    irregularity_level: float = 0.0,
    rng: np.random.Generator | None = None,
) -> list[float]:
    """Keep the first dispatch and vary subsequent intervals without reordering.

    Supply StreamManager.get_stream("disruptions") for nonzero irregularity.
    Level zero returns the original times without consuming random draws.
    For a nominal headway H, the target variance is (H * level)**2 seconds².
    This describes requested spacing; operational separation and suspensions
    can change the headways that are actually realised.
    """
    if (
        isinstance(irregularity_level, bool)
        or not isinstance(irregularity_level, int | float)
        or not math.isfinite(irregularity_level)
        or irregularity_level < 0
    ):
        raise ValueError("Irregularity level must be finite and non-negative")
    times = list(departure_times_s)
    if any(not math.isfinite(t) or t < 0 for t in times):
        raise ValueError("Dispatch times must be finite and non-negative")
    if any(b <= a for a, b in zip(times, times[1:], strict=False)):
        raise ValueError("Dispatch times must be strictly increasing")
    if irregularity_level == 0:
        return times
    if rng is None:
        raise ValueError("Spacing perturbation requires a seeded disruptions stream")
    if len(times) < 2:
        return times

    # log(1 + level²), evaluated without overflowing level².
    sigma_squared = (
        math.log1p(irregularity_level * irregularity_level)
        if irregularity_level <= 1
        else 2 * math.log(math.hypot(1.0, irregularity_level))
    )
    multipliers = rng.lognormal(
        -sigma_squared / 2, math.sqrt(sigma_squared), len(times) - 1
    )
    perturbed = [times[0]]
    for previous, current, multiplier in zip(
        times, times[1:], multipliers, strict=False
    ):
        next_s = perturbed[-1] + (current - previous) * float(multiplier)
        if not math.isfinite(next_s) or next_s <= perturbed[-1]:
            raise ValueError(
                "Perturbed dispatch times must remain finite and increasing"
            )
        perturbed.append(next_s)
    return perturbed
