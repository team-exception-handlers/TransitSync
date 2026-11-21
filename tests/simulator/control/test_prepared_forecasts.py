# AI contribution: 50% or more AI-generated
"""Prepared forecast reuse agrees exactly with the standalone public evaluator.

Reuse must stay inside one immutable observation. These properties exercise
different holds and horizon clipping against the original downstream arithmetic.
Non-integer cost weights expose changes in summation order that integer-only
examples could miss. Repeated candidates check cache isolation explicitly.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from simulator.control.break_even import BreakEvenWeights
from simulator.control.downstream import (
    evaluate_downstream,
    prepare_downstream,
    prepare_projection,
    project_visits,
)
from tests.simulator.control.downstream_helpers import harmful_snapshot
from tests.simulator.control.rolling_helpers import snapshot
from tests.simulator.control.test_rolling_horizon import planner


@given(st.integers(0, 300), st.integers(0, 300), st.integers(300, 1200))
@settings(max_examples=30)
def test_prepared_candidates_match_standalone_costs(first, second, end_s):
    """Graph/marginal-cost caches must not retain a preceding candidate's hold."""
    observation = harmful_snapshot()
    project = prepare_projection(observation, end_s)
    baseline = project({})
    weights = BreakEvenWeights(w_wait=1.3, w_onboard=0.7)
    score = prepare_downstream(baseline, observation, weights, end_s)
    ordered_score = prepare_downstream(
        baseline, observation, weights, end_s, ordered=True
    )
    for hold in (first, second, first):
        holds = {("A", 0, 0): hold}
        candidate = project(holds)
        assert candidate == project_visits(observation, holds, end_s)
        assert score(candidate) == evaluate_downstream(
            baseline, candidate, observation, weights, end_s
        )
        assert ordered_score(candidate) == score(candidate)
        assert score(candidate[::-1]) == score(candidate)
        assert score(candidate[:-1]) == evaluate_downstream(
            baseline, candidate[:-1], observation, weights, end_s
        )


def test_reused_planner_starts_fresh_after_the_observation_changes():
    """A new load may change the optimum; caches cannot outlive the decision."""
    policy = planner()
    useful = policy.plan(snapshot(load=10))
    expensive = policy.plan(snapshot(load=200))
    assert useful.hold_s == 10
    assert expensive.hold_s == 0
    assert expensive == planner().plan(snapshot(load=200))
