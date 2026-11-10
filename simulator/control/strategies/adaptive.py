# AI contribution: 50% or more AI-generated
"""Switch between connection protection and headway regulation (#64)."""

from typing import Any

from simulator.control.interface import (
    DecisionController,
    HoldAction,
    ObservationSnapshot,
)
from simulator.control.strategies.connection_protection import (
    ConnectionProtectionStrategy,
)
from simulator.control.strategies.headway_regulation import HeadwayRegulationStrategy
from simulator.control.validation import finite_number


class AdaptiveStrategy(DecisionController):
    """Select a policy for each line and directional platform."""

    name = "adaptive"

    def __init__(
        self,
        connection: ConnectionProtectionStrategy,
        headway: HeadwayRegulationStrategy,
        threshold: float,
    ) -> None:
        self._connection = connection
        self._headway = headway
        self._threshold = validate_irregularity_threshold(threshold)
        self._modes: dict[tuple[str, str], str] = {}

    def evaluate(self, observation: ObservationSnapshot) -> tuple[HoldAction, ...]:
        """Select and run the policy using the latest completed headways."""
        train = next(
            (t for t in observation.trains if t.train_id == observation.train_id),
            None,
        )
        if train is None:
            raise ValueError(f"Missing deciding train {observation.train_id!r}")

        scope = (train.line_id, observation.platform_id)
        previous = self._modes.get(scope, self._connection.name)
        current = previous
        score = observation.service_irregularity

        # An unavailable score leaves the previous mode in effect.
        if score is not None:
            current = (
                self._headway.name if score > self._threshold else self._connection.name
            )
            if current != previous:
                self._modes[scope] = current
                self._connection.audit.record_mode_switch(
                    observation,
                    line_id=train.line_id,
                    from_mode=previous,
                    to_mode=current,
                    irregularity=score,
                    threshold=self._threshold,
                )
        strategy = self._headway if current == self._headway.name else self._connection
        return strategy.evaluate(observation)

    def decision_records(self) -> tuple[dict[str, Any], ...]:
        """Return switch and connection decision records in evaluation order."""
        return self._connection.audit.decision_records()


def validate_irregularity_threshold(value: object) -> float:
    """Return a finite, nonnegative threshold for the dimensionless score."""
    label = "control.irregularity_threshold"
    try:
        return finite_number(label, value, minimum=0.0)
    except OverflowError as error:
        raise ValueError(f"{label}: must be finite") from error
