# AI contribution: 50% or more AI-generated
"""Shared deterministic forecasts for downstream and coordinated tests."""

from dataclasses import replace

from simulator.control.break_even import BreakEvenWeights
from simulator.control.downstream import evaluate_downstream, project_visits
from tests.simulator.control.rolling_helpers import snapshot, visit


def forecast(seen, hold=10, end=1000):
    baseline = project_visits(seen, {}, end)
    candidate = project_visits(seen, {("A", 0, 0): hold}, end)
    cost = evaluate_downstream(baseline, candidate, seen, BreakEvenWeights(), end)
    return baseline, candidate, cost


def cascade():
    visits = (
        visit(),
        visit("A", "P2", 210, index=1),
        visit("A", "P3", 310, index=2),
        visit("B", "P1", 115),
        visit("B", "P2", 225, index=1),
        visit("B", "P3", 325, index=2),
    )
    seen = snapshot(visits)
    return replace(
        seen,
        trains=tuple(
            replace(t, onboard_load=100 if t.train_id == "B" else 10)
            for t in seen.trains
        ),
    )


def harmful_snapshot():
    seen = snapshot(
        (
            visit(),
            visit("A", "P2", 510, index=1),
            visit("B", "P1", 300),
            visit("B", "P2", 520, index=1),
        )
    )
    return replace(
        seen,
        minimum_gap_s=10,
        trains=tuple(
            replace(t, onboard_load=500 if t.train_id == "B" else 10)
            for t in seen.trains
        ),
    )
