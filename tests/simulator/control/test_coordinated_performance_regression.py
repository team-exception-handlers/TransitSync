# AI contribution: 50% or more AI-generated
"""Byte-level oracles captured from main 8ddf153 before optimization.

These seeded real runs protect all event and audit fields, numeric encoding,
record order, and explanations. Expected hashes are fixed baseline artifacts,
not values recalculated by the implementation under test.
Event hashes include every processed passenger movement and actual departure.
Audit hashes include reasons, alternative scores, plan order and search counts.
Both exact and approximate searches must retain their original encoding.
Update these constants only for an independently reviewed behavior change,
never to make a performance optimization pass its regression checks.
"""

import hashlib
import json

import pytest

from simulator.control.planning import RollingHorizonSettings
from simulator.control.rolling_horizon import RollingHorizonPlanner
from simulator.control.strategies.rolling_horizon import RollingHorizonStrategy
from tests.simulator.control.test_coordinated_run import run_harmful
from tests.simulator.control.test_rolling_horizon_review import independent_stations
from tests.simulator.control.test_rolling_horizon_run import run


@pytest.mark.parametrize(
    ("options", "events", "decisions"),
    [
        (
            {},
            "d7d61924c6955f96781bce09bba1526f38f3afb0d106e2ceffb4e77fb70bda8c",
            "cf89edc8028924296e7bd5614f1d2094206c9f7124bad14dfbde8c00269b2637",
        ),
        (
            {"with_errors": True},
            "dda8d8e16b2a5adf3b60fb96773122cc5ce84a94529218163269bfb277851ae7",
            "52966eac82ab118f879da856a087e624a376ec2564a6af811469fa73f225738b",
        ),
        (
            {"cap": 5},
            "748abcee65f0d38cb32e292af3f1a0b52509612d39383b568cda1b47e7c1813a",
            "e358a43cef4c87b6de2d6d1144f99a144b8219d6ddbe01ed79df11208814fdd7",
        ),
    ],
    ids=["exact", "prediction-errors", "rule-clamp"],
)
def test_coordinated_logs_match_unoptimized_baseline(
    tmp_path, options, events, decisions
):
    """Retain exact bytes through real transfers, error draws and rule clamping."""
    result, _, _ = run(tmp_path, **options)
    assert hashlib.sha256(result.events_path.read_bytes()).hexdigest() == events
    assert hashlib.sha256(result.decisions_path.read_bytes()).hexdigest() == decisions


def test_downstream_refusal_matches_unoptimized_baseline(tmp_path):
    """A locally useful hold must retain its downstream refusal and full audit."""
    _, result = run_harmful(tmp_path, 600)
    assert hashlib.sha256(result.events_path.read_bytes()).hexdigest() == (
        "a6e7c0b76170e27dff0e9f7399bb4c3b6e11fbcf98688943df85bd14a8db8419"
    )
    assert hashlib.sha256(result.decisions_path.read_bytes()).hexdigest() == (
        "65634e6e82e577268474ea0a5e41f3d4dbe0e3810e251797123dd7d5eace210e"
    )


def test_approximate_search_audit_matches_unoptimized_baseline():
    """The bounded search retains candidate counts, tie-breaking and all fields."""
    observation, walking = independent_stations(7)
    strategy = RollingHorizonStrategy(
        RollingHorizonPlanner(walking, RollingHorizonSettings(max_combinations=100))
    )
    strategy.evaluate(observation)
    encoded = json.dumps(strategy.decision_records(), separators=(",", ":")).encode()
    assert hashlib.sha256(encoded).hexdigest() == (
        "a5851fb90d54b2612552ea283e412d9edc3f5c88ea9fc22f68f0154e05e7c799"
    )
