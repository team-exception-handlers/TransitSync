# AI contribution: 50% or more AI-generated
"""Walking time sampling module for passenger pedestrian movement."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import numpy as np

    from simulator.engine.random_streams import StreamManager


class WalkingTimeSampler:
    """Samples pedestrian walking durations using the isolated
    'walking_times' stream."""

    def __init__(
        self, stream_manager: StreamManager, default_mean: float = 300.0
    ) -> None:
        self._stream = stream_manager.get_stream("walking_times")
        self._default_mean = default_mean

    def sample(
        self,
        size: int | None = None,
        mean: float | None = None,
        min_time: float = 30.0,
    ) -> float | np.ndarray:
        """Sample walking durations in seconds bounded by min_time
        using NumPy exponential distribution."""
        target_mean = mean if mean is not None else self._default_mean
        # NumPy exponential distribution (scale = mean = 1.0 / rate)
        raw_samples = self._stream.exponential(scale=target_mean, size=size)
        return np.maximum(min_time, raw_samples)
