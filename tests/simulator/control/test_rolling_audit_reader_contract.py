# AI contribution: 50% or more AI-generated
"""Public Coordinated audit records keep their committed shape and isolation.

``RollingHorizonStrategy`` now stores encoded JSON lines and decodes them for
``decision_records()``, where it used to return deep copies of dictionaries.
That is only equivalent if the original dictionaries already held plain JSON
types: no tuples, no NumPy scalars, no float subclasses. These tests check
that shape directly from the dataclasses the record is built from, then check
that every public record equals its log line and is detached from storage.
"""

import json
from dataclasses import asdict

import pytest

from simulator.control.hold_search import HoldSearchSettings
from simulator.control.planning import RollingHorizonSettings
from simulator.control.rolling_horizon import RollingHorizonPlanner
from simulator.control.strategies.rolling_horizon import RollingHorizonStrategy
from simulator.control.walking_cdf import ShiftedExponentialCdf
from tests.simulator.control.downstream_helpers import cascade, harmful_snapshot

JSON_LEAVES = (str, int, float, bool, type(None))


def _plain_json(value):
    """True when every container is dict/list and every leaf a JSON scalar."""
    if isinstance(value, dict):
        return all(type(k) is str and _plain_json(v) for k, v in value.items())
    if type(value) is list:
        return all(_plain_json(v) for v in value)
    return type(value) in JSON_LEAVES


def _strategy(window_s=1000):
    seen = harmful_snapshot()
    walks = {v.platform_id: ShiftedExponentialCdf(120, 30) for v in seen.future_visits}
    return RollingHorizonStrategy(
        RollingHorizonPlanner(
            walks,
            RollingHorizonSettings(window_s, 999),
            HoldSearchSettings(step_s=5, max_hold_s=300),
        )
    )


@pytest.fixture
def evaluated():
    """One strategy after planning two different observations."""
    strategy = _strategy()
    strategy.evaluate(harmful_snapshot())
    strategy.evaluate(cascade())
    return strategy


def test_committed_record_parts_never_contained_tuples():
    """The deep-copied dictionaries were already plain JSON before encoding."""
    plan = _strategy().planner.plan(harmful_snapshot())
    parts = [asdict(a) for a in plan.alternatives] + [asdict(d) for d in plan.decisions]
    assert parts
    assert all(_plain_json(part) for part in parts)


def test_public_records_are_plain_json_equal_to_their_log_lines(evaluated):
    records = evaluated.decision_records()
    lines = [json.loads(r.line) for r in evaluated.encoded_decision_records()]
    assert len(records) == 2
    assert list(records) == lines
    assert all(_plain_json(record) for record in records)


def test_records_carry_nonzero_alternatives_and_plan_visits(evaluated):
    """The shape checks above cover populated nested lists, not empty ones."""
    for record in evaluated.decision_records():
        assert any(alt["hold_s"] > 0 for alt in record["alternatives"])
        assert record["plan"]


def test_mutating_a_returned_record_does_not_change_storage(evaluated):
    first = evaluated.decision_records()
    first[0]["alternatives"].clear()
    first[0]["plan"][0]["visit"]["train_id"] = "changed"
    second = evaluated.decision_records()
    assert second[0]["alternatives"]
    assert second[0]["plan"][0]["visit"]["train_id"] != "changed"
