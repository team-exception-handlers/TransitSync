# AI contribution: 50% or more AI-generated
"""Rule checking and enforcement layer for transit control actions
(US-2.4, US-2.5, Task 2.4.1, Task 2.5.4, #50, #57).
"""

from __future__ import annotations

from collections.abc import Sequence

from simulator.control.interface import HoldAction
from simulator.control.settings import OperatingRulesConfig


class RuleViolationError(ValueError):
    """Raised when an action violates an unclampable operating rule."""


def enforce_operating_rules(
    actions: Sequence[HoldAction],
    rules: OperatingRulesConfig,
) -> tuple[HoldAction, ...]:
    """Evaluate proposed control actions against centralized operating rules.

    Applies clamping or refusal based on the scenario's ``rule_action_map``.
    """
    filtered_actions: list[HoldAction] = []

    for action in actions:
        # Check duration fields robustly in order of likelihood
        duration = getattr(
            action,
            "duration_s",
            getattr(action, "duration", getattr(action, "hold_s", 0.0)),
        )

        # 1. Check max_hold_time violation
        if duration > rules.max_hold_time:
            action_type = rules.rule_action_map.get("max_hold_exceeded", "CLAMP")
            if action_type == "REFUSE":
                # Drop the action entirely (refuse)
                continue
            elif action_type == "CLAMP":
                new_reason = (
                    f"{action.reason} (clamped to max_hold_time {rules.max_hold_time}s)"
                )
                # Reconstruct HoldAction while preserving its initialization format.
                if hasattr(action, "duration_s"):
                    action = HoldAction(
                        train_id=action.train_id,
                        duration_s=rules.max_hold_time,
                        reason=new_reason,
                    )
                elif hasattr(action, "hold_s"):
                    action = HoldAction(
                        train_id=action.train_id,
                        hold_s=rules.max_hold_time,
                        reason=new_reason,
                    )
                else:
                    action = HoldAction(
                        action.train_id, rules.max_hold_time, new_reason
                    )
            else:
                raise RuleViolationError(
                    f"Unknown action type {action_type!r} for max_hold_exceeded"
                )

        filtered_actions.append(action)

    return tuple(filtered_actions)
