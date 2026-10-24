# AI contribution: 50% or more AI-generated
"""Train delay disruptions for US-1.5 #26; all times and delays are seconds."""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DelayInjection:
    """Add a fixed delay to the first matching arrival at or after ``time_s``.

    ``platform_id`` selects the physical location. Optional station and train
    IDs narrow the target without coupling the delay magnitude to its location.
    """

    disruption_id: str
    time_s: float
    delay_s: float
    platform_id: str
    station_id: str | None = None
    train_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.disruption_id, str) or not self.disruption_id.strip():
            raise ValueError("Disruption ID cannot be empty")
        if not isinstance(self.platform_id, str) or not self.platform_id.strip():
            raise ValueError("Disruption platform ID cannot be empty")
        for field_name in ("station_id", "train_id"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"Disruption {field_name} cannot be empty")
        if (
            isinstance(self.time_s, bool)
            or not isinstance(self.time_s, int | float)
            or not math.isfinite(self.time_s)
            or self.time_s < 0
        ):
            raise ValueError("Disruption time_s must be finite and non-negative")
        if (
            isinstance(self.delay_s, bool)
            or not isinstance(self.delay_s, int | float)
            or not math.isfinite(self.delay_s)
            or self.delay_s <= 0
        ):
            raise ValueError("Disruption delay_s must be finite and positive")

    def matches(
        self,
        *,
        train_id: str,
        station_id: str,
        platform_id: str,
        arrival_s: float,
    ) -> bool:
        """Whether this arrival is the first eligible target for the delay."""
        return (
            arrival_s >= self.time_s
            and platform_id == self.platform_id
            and (self.station_id is None or station_id == self.station_id)
            and (self.train_id is None or train_id == self.train_id)
        )

    def to_manifest_record(self) -> dict[str, str | float | None]:
        """Return the immutable configured values for ``manifest.json``."""
        return {
            "id": self.disruption_id,
            "type": "delay",
            "time_s": float(self.time_s),
            "delay_s": float(self.delay_s),
            "train_id": self.train_id,
            "station_id": self.station_id,
            "platform_id": self.platform_id,
        }
