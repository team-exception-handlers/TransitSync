# AI contribution: 50% or more AI-generated
"""Decision pipeline: snapshot, error, strategy, then rule check (#38, #39, #46).

Design pattern: Facade. ``TrainComponent`` makes one call at ``DepartureDue``
and gets back the hold to apply, without knowing the parts behind it.
The strategy sees estimates with prediction error (section 7), while the rule
check still uses the true snapshot, since safety rules are the simulator's.
"""

import copy
import math
from dataclasses import dataclass
from typing import Any, Protocol

from simulator.control.decision_audit import DecisionAuditSource, estimates_record
from simulator.control.interface import (
    DecisionController,
    HoldAction,
    ObservationSnapshot,
)
from simulator.control.observation_builder import ObservationBuilder, TrainSource
from simulator.control.planning import RollingHorizonSettings
from simulator.control.prediction_error import PredictionErrorModel
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
    """Runs one strategy at every decision point; no control by default.

    Without ``error_model`` the strategy sees true values. A run built from a
    scenario passes one made from ``control.prediction_error`` and the
    ``prediction_errors`` stream.
    """

    def __init__(
        self,
        strategy: DecisionController | None = None,
        builder: ObservationBuilder | None = None,
        enforcer: ConstraintEnforcer | None = None,
        error_model: PredictionErrorModel | None = None,
    ) -> None:
        self.strategy = strategy or NoControlStrategy()
        self._builder = builder or ObservationBuilder()
        self._enforcer = enforcer or PassThroughEnforcer()
        self._error_model = error_model
        self._estimates: list[dict[str, Any]] = []

    def decide(
        self, decision: DepartureDue, trains: TrainSource
    ) -> HoldDecision | None:
        """Return the hold for the train at ``decision``, or ``None`` to leave.

        Raises:
            ValueError: the strategy asked to hold another train, or more than
                once; a hold can only start at that train's own decision point.
        """
        # The stacked rolling strategy owns a planner with these settings;
        # planning probes without one use the same documented default window.
        planning = getattr(self.strategy, "requires_future_visits", False)
        until_s = math.inf
        if planning:
            planner = getattr(self.strategy, "planner", None)
            settings = getattr(planner, "settings", RollingHorizonSettings())
            until_s = decision.time_s + settings.window_s
        truth = self._builder.build(
            decision,
            trains,
            planning=planning,
            until_s=until_s,
        )
        seen = truth
        if self._error_model:
            seen = self._error_model.apply(truth)
            # Recorded before the strategy runs, so declines are audited too
            self._estimates.append(estimates_record(truth, seen))
        actions = self.strategy.evaluate(seen)
        if not actions:
            return None
        if len(actions) > 1 or actions[0].train_id != decision.train_id:
            raise ValueError(
                f"{self.strategy.name} may only hold {decision.train_id} once here"
            )
        return self._enforcer.validate(actions[0], truth)

    def decision_records(self) -> tuple[dict[str, Any], ...]:
        """Return the strategy's audit records (#44), then any estimates (#39).

        The ``Hold`` event already records what the rules applied, so the
        audit only needs the strategy's reasoning and what it saw.
        """
        own: tuple[dict[str, Any], ...] = ()
        if isinstance(self.strategy, DecisionAuditSource):
            own = tuple(self.strategy.decision_records())
        # Copies, so a caller cannot change what is written to the audit log
        return own + tuple(copy.deepcopy(self._estimates))
