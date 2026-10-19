# AI contribution: 50% or more AI-generated
"""Transit vehicle run time sampling module."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulator.engine.random_streams import StreamManager


class RunTimeSampler:
    """Samples transit vehicle link run times using the isolated 'run_times' stream."""

    def __init__(self, stream_manager: StreamManager) -> None:
        self._stream = stream_manager.get_stream("run_times")

    def sample_runtime(self, scheduled_time: float, variability: float = 0.1) -> float:
        """Sample an actual run time based on scheduled time and variability."""
        if scheduled_time <= 0:
            return 0.0
        multiplier = self._stream.normal(loc=1.0, scale=variability)
        sampled_time = scheduled_time * max(0.5, float(multiplier))
        return round(sampled_time, 2)
