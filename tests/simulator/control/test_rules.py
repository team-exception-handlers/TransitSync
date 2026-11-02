# AI contribution: 50% or more AI-generated
"""Tests for operating rules enforcement and rule checking
(US-2.4, US-2.5, Task 2.4.1, Task 2.5.4, #50, #57).
"""

import pytest

from simulator.control.interface import HoldAction
from simulator.control.rules import RuleViolationError, enforce_operating_rules
from simulator.control.settings import OperatingRulesConfig


def test_action_within_limits_passes_unmodified():
    rules = OperatingRulesConfig(max_hold_time=300.0)
    action = HoldAction(train_id="train_1", duration_s=120.0, reason="test")

    result = enforce_operating_rules((action,), rules)
    assert len(result) == 1
    duration = getattr(
        result[0],
        "duration_s",
        getattr(result[0], "hold_s", 0.0),
    )
    assert duration == 120.0


def test_max_hold_exceeded_clamps_when_configured():
    rules = OperatingRulesConfig(
        max_hold_time=100.0, rule_action_map={"max_hold_exceeded": "CLAMP"}
    )
    action = HoldAction(train_id="train_1", duration_s=120.0, reason="test")

    result = enforce_operating_rules((action,), rules)
    assert len(result) == 1
    duration = getattr(
        result[0],
        "duration_s",
        getattr(result[0], "hold_s", 0.0),
    )
    assert duration == 100.0
    assert "clamped" in result[0].reason


def test_max_hold_exceeded_refuses_when_configured():
    rules = OperatingRulesConfig(
        max_hold_time=100.0, rule_action_map={"max_hold_exceeded": "REFUSE"}
    )
    action = HoldAction(train_id="train_1", duration_s=120.0, reason="test")

    result = enforce_operating_rules((action,), rules)
    assert len(result) == 0  # Action is dropped / refused


def test_multiple_actions_mixed_compliance():
    """Verify that a mix of compliant and non-compliant actions are processed."""
    rules = OperatingRulesConfig(
        max_hold_time=100.0,
        rule_action_map={"max_hold_exceeded": "CLAMP"},
    )
    actions = (
        HoldAction(train_id="train_1", duration_s=50.0, reason="fine"),
        HoldAction(train_id="train_2", duration_s=150.0, reason="too_long"),
    )
    result = enforce_operating_rules(actions, rules)
    assert len(result) == 2
    assert result[0].duration_s == 50.0
    assert result[1].duration_s == 100.0


def test_unknown_rule_action_raises_error():
    """Verify that an unsupported action type in the map raises a RuleViolationError."""
    rules = OperatingRulesConfig(
        max_hold_time=100.0,
        rule_action_map={"max_hold_exceeded": "EXPLODE"},
    )
    action = HoldAction(train_id="train_1", duration_s=150.0, reason="too_long")

    with pytest.raises(RuleViolationError, match="Unknown action type"):
        enforce_operating_rules((action,), rules)
