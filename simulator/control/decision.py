# AI contribution: 50% or more AI-generated
"""Decision pipeline: snapshot, strategy, then rule check (#38, #46).

Design pattern: Facade. ``TrainComponent`` makes one call at ``DepartureDue``
and gets back the hold to apply, without knowing the parts behind it.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from simulator.control.decision_audit import DecisionAuditSource
from simulator.control.interface import (
    DecisionController,
    HoldAction,
    ObservationSnapshot,
)
from simulator.control.observation_builder import ObservationBuilder, TrainSource
from simulator.control.strategies.no_control import NoControlStrategy
from simulator.engine.events import DepartureDue


@dataclass(frozen=True, slots=True)
class HoldDecision:
    """What the strategy asked for and what the rules allowed, in seconds."""

    requested_s: float
    applied_s: float
    reason: str


class ConstraintEnforcer(Protocol):
    """Safety rules (US-2.5, #57) that may shorten or refuse a requested hold."""

    def validate(
        self, action: HoldAction, observation: ObservationSnapshot
    ) -> HoldDecision: ...


class PassThroughEnforcer:
    """Approves every hold unchanged until the rule checking layer (#57) exists."""

    def validate(
        self, action: HoldAction, observation: ObservationSnapshot
    ) -> HoldDecision:
        return HoldDecision(action.duration_s, action.duration_s, action.reason)


class DecisionPipeline:
    """Runs one strategy at every decision point; no control by default."""

    def __init__(
        self,
        strategy: DecisionController | None = None,
        builder: ObservationBuilder | None = None,
        enforcer: ConstraintEnforcer | None = None,
    ) -> None:
        self.strategy = strategy or NoControlStrategy()
        self._builder = builder or ObservationBuilder()
        self._enforcer = enforcer or PassThroughEnforcer()

    def decide(
        self, decision: DepartureDue, trains: TrainSource
    ) -> HoldDecision | None:
        """Return the hold for the train at ``decision``, or ``None`` to leave.

        Raises:
            ValueError: the strategy asked to hold another train, or more than
                once; a hold can only start at that train's own decision point.
        """
        observation = self._builder.build(decision, trains)
        actions = self.strategy.evaluate(observation)
        if not actions:
            return None
        if len(actions) > 1 or actions[0].train_id != decision.train_id:
            raise ValueError(
                f"{self.strategy.name} may only hold {decision.train_id} once here"
            )
        return self._enforcer.validate(actions[0], observation)

    def decision_records(self) -> tuple[dict[str, Any], ...]:
        """Return the strategy's audit records (#44); none if it keeps none.

        The ``Hold`` event already records what the rules applied, so the
        audit only needs the strategy's own reasoning.
        """
        if isinstance(self.strategy, DecisionAuditSource):
            return tuple(self.strategy.decision_records())
        return ()
