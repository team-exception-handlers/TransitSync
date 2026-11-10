# AI contribution: 50% or more AI-generated
"""Measure recent departure headway deviation for Issue #63."""

import math
from collections import defaultdict, deque
from collections.abc import Mapping
from statistics import mean

from simulator.engine.events import TrainDeparture


class ServiceIrregularity:
    """Track a rolling average per line and directional platform for one run.

    Targets in seconds and the window length come from validated control
    settings. Without a fixed target, use the timetable gap for the same pair
    of departed trains.

    The sccore measures deviation from the target. Current scenario settings provide
    fixed targets for headway regulation and timetable gaps for other strategies.
    Identical departures can therefore produce different scores. For cross-strategy
    comparisons, evaluate all runs against the same reference and window size.
    """

    def __init__(
        self, window_size: int, target_headways_s: Mapping[str, float] | None = None
    ) -> None:
        self._targets = dict(target_headways_s or {})
        self._last_departure: dict[tuple[str, str], tuple[float, float]] = {}
        self._deviations: dict[tuple[str, str], deque[float]] = defaultdict(
            lambda: deque(maxlen=window_size)
        )
        self._values: dict[tuple[str, str], float] = {}

    def record_departure(self, event: TrainDeparture, line_id: str) -> None:
        """Update from a completed departure in simulation order."""
        scope = (line_id, event.platform_id)
        previous = self._last_departure.get(scope)
        self._last_departure[scope] = (event.time_s, event.scheduled_s)
        if previous is None:
            return
        previous_actual_s, previous_scheduled_s = previous
        actual_s = event.time_s - previous_actual_s
        target_s = self._targets.get(event.platform_id)
        if target_s is None:
            target_s = event.scheduled_s - previous_scheduled_s
        if target_s <= 0:
            return
        deviation = abs(actual_s - target_s) / target_s
        if math.isfinite(deviation):
            window = self._deviations[scope]
            window.append(deviation)
            self._values[scope] = mean(window)

    def value(self, line_id: str, platform_id: str) -> float | None:
        """Return the cached dimensionless mean, or None before a valid gap."""
        return self._values.get((line_id, platform_id))
