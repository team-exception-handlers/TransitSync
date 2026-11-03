# AI contribution: 50% or more AI-generated
"""Tests for operating rules enforcement and rule checking
(US-2.4, US-2.5, Task 2.4.1, Task 2.5.4, #50, #57).
"""

import pytest

from simulator.control.interface import HoldAction
from simulator.control.rules import OperatingRulesEnforcer, RuleViolationError
from simulator.control.settings import OperatingRulesConfig


def test_action_within_limits_passes_unmodified():
    rules = OperatingRulesConfig(max_hold_time=300.0)
    enforcer = OperatingRulesEnforcer(rules)
    action = HoldAction(train_id="train_1", duration_s=120.0, reason="test")

    decision = enforcer.validate(action)
    assert decision.requested_s == 120.0
    assert decision.applied_s == 120.0
    assert decision.reason == "test"


def test_max_hold_exceeded_clamps_when_configured():
    rules = OperatingRulesConfig(
        max_hold_time=100.0, rule_action_map={"max_hold_exceeded": "CLAMP"}
    )
    enforcer = OperatingRulesEnforcer(rules)
    action = HoldAction(train_id="train_1", duration_s=120.0, reason="test")

    decision = enforcer.validate(action)
    assert decision.requested_s == 120.0
    assert decision.applied_s == 100.0
    assert "clamped" in decision.reason


def test_max_hold_exceeded_refuses_when_configured():
    rules = OperatingRulesConfig(
        max_hold_time=100.0, rule_action_map={"max_hold_exceeded": "REFUSE"}
    )
    enforcer = OperatingRulesEnforcer(rules)
    action = HoldAction(train_id="train_1", duration_s=120.0, reason="test")

    decision = enforcer.validate(action)
    assert decision.requested_s == 120.0
    assert decision.applied_s == 0.0
    assert "refused" in decision.reason


def test_unknown_rule_action_raises_error():
    rules = OperatingRulesConfig(
        max_hold_time=100.0, rule_action_map={"max_hold_exceeded": "INVALID"}
    )
    enforcer = OperatingRulesEnforcer(rules)
    action = HoldAction(train_id="train_1", duration_s=120.0, reason="test")

    with pytest.raises(RuleViolationError, match="Unknown action type"):
        enforcer.validate(action)
