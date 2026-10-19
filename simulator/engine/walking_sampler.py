# AI contribution: 50% or more AI-generated
"""Walking time sampling module for passenger pedestrian movement."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from simulator.engine.random_streams import StreamManager


class WalkingTimeSampler:
    """Samples pedestrian walking durations using a shifted exponential distribution
    over the isolated 'walking_times' stream.

    Modeling Choice:
        Walking times are modeled using a shifted exponential distribution:
        `min_time + Exponential(scale = mean - min_time)`. This guarantees an
        absolute lower bound (`min_time`) without creating an unnatural statistical
        spike at the boundary, while perfectly preserving the target mean.
    """

    def __init__(
        self, stream_manager: StreamManager, default_mean: float = 300.0
    ) -> None:
        if (
            isinstance(default_mean, bool)
            or not isinstance(default_mean, int | float)
            or not math.isfinite(default_mean)
            or default_mean <= 0
        ):
            raise ValueError("default_mean must be a finite number > 0")
        self._stream = stream_manager.get_stream("walking_times")
        self._default_mean = float(default_mean)

    def sample(
        self,
        size: int | None = None,
        mean: float | None = None,
        min_time: float = 30.0,
    ) -> float | np.ndarray:
        """Sample walking durations using a shifted exponential distribution.

        Args:
            size: Optional sample size or shape.
            mean: Target mean walking duration in seconds (must be finite > min_time).
            min_time: Absolute lower bound floor in seconds (must be finite >= 0).

        Returns:
            A single float or NumPy array of sampled walking durations.
        """
        if (
            isinstance(min_time, bool)
            or not isinstance(min_time, int | float)
            or not math.isfinite(min_time)
            or min_time < 0
        ):
            raise ValueError("min_time must be a finite number >= 0")
        floor_time = float(min_time)

        if mean is not None:
            if (
                isinstance(mean, bool)
                or not isinstance(mean, int | float)
                or not math.isfinite(mean)
                or mean <= floor_time
            ):
                raise ValueError(
                    f"mean must be a finite number > min_time ({floor_time})"
                )
            target_mean = float(mean)
        else:
            target_mean = max(self._default_mean, floor_time + 1.0)

        # Shifted exponential scale: scale = mean - min_time
        scale = target_mean - floor_time
        raw_samples = self._stream.exponential(scale=scale, size=size)
        return floor_time + raw_samples
