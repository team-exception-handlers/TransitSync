# AI contribution: 50% or more AI-generated
"""Rule checking and enforcement layer for transit control actions
(US-2.4, US-2.5, Task 2.4.1, Task 2.5.4, Task 2.4.4, #50, #57, #53, #58).
"""

from __future__ import annotations

from simulator.control.decision import HoldDecision
from simulator.control.interface import HoldAction, ObservationSnapshot
from simulator.control.settings import OperatingRulesConfig


class RuleViolationError(ValueError):
    """Raised when an action violates an unclampable operating rule."""


class OperatingRulesEnforcer:
    """Enforces scenario operating rules and connection

    protection on control actions (US-2.4, US-2.5, #53, #57, #58).
    """

    def __init__(self, rules: OperatingRulesConfig) -> None:
        self.rules = rules

    def validate(
        self,
        action: HoldAction,
        observation: ObservationSnapshot | None = None,
    ) -> HoldDecision:
        """Validate a proposed HoldAction against operating rules,

        one-hop constraints, and apply clamping/refusal strategies.
        """
        duration = action.duration_s

        # Task 2.4.4 (#53): One-hop constraint check
        target_train = getattr(observation, "target_train", None)
        is_delayed = getattr(target_train, "system_delayed", False) or getattr(
            observation, "target_train_system_delayed", False
        )
        if observation and is_delayed:
            return HoldDecision(
                requested_s=duration,
                applied_s=0.0,
                reason="refused: one-hop constraint violation "
                "(train already system-delayed)",
            )

        limit = self.rules.max_hold_time

        if duration <= limit:
            return HoldDecision(
                requested_s=duration,
                applied_s=duration,
                reason=action.reason,
            )

        action_type = self.rules.rule_action_map.get("max_hold_exceeded", "CLAMP")

        if action_type == "REFUSE":
            return HoldDecision(
                requested_s=duration,
                applied_s=0.0,
                reason=f"refused: over max hold {limit:g} s ({action.reason})",
            )
        elif action_type == "CLAMP":
            return HoldDecision(
                requested_s=duration,
                applied_s=limit,
                reason=f"{action.reason} (clamped to max_hold_time {limit:g} s)",
            )
        else:
            raise RuleViolationError(
                f"Unknown action type {action_type!r} for max_hold_exceeded"
            )
