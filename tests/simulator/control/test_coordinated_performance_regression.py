# AI contribution: 50% or more AI-generated
"""Byte-level oracles captured from unoptimized main before optimization.

These seeded real runs protect all event and audit fields, numeric encoding,
record order, and explanations. Expected hashes are fixed baseline artifacts,
not values recalculated by the implementation under test.
Event hashes include every processed passenger movement and actual departure.
Audit hashes include reasons, alternative scores, plan order and search counts.
Both exact and approximate searches must retain their original encoding.
Update these constants only for an independently reviewed behavior change,
never to make a performance optimization pass its regression checks.

The three seeded runs were recaptured from main c1f3d0a, which keys every
prediction error by what it predicts (#192), so they replace the older 8ddf153
values. Decision logs keep one hash per platform. Windows and glibc Linux round
``math.erfc``, ``math.expm1`` and ``math.log`` differently in the last bit, so
``net_ps`` costs can differ by about 2e-16 relative while every decision, plan
and count is identical; with keyed draws only the prediction-error run shows
it. Both hashes come from running c1f3d0a itself, on Windows and in
``python:3.12-slim`` (glibc 2.41), never from the optimized code. The two
single-run oracles below that still match 8ddf153 were not affected by #192.
"""

import hashlib
import json
import sys

import pytest

from simulator.control.planning import RollingHorizonSettings
from simulator.control.rolling_horizon import RollingHorizonPlanner
from simulator.control.strategies.rolling_horizon import RollingHorizonStrategy
from tests.simulator.control.test_coordinated_run import run_harmful
from tests.simulator.control.test_rolling_horizon_review import independent_stations
from tests.simulator.control.test_rolling_horizon_run import run

# Baseline decision-log hashes from c1f3d0a, keyed by run and then sys.platform
_DECISION_HASHES = {
    "exact": {
        "win32": "9b5e0b89ab8dc32e1f92454303f40940919a55ba676a4e434de6443020e4372b",
        "linux": "9b5e0b89ab8dc32e1f92454303f40940919a55ba676a4e434de6443020e4372b",
    },
    "prediction-errors": {
        "win32": "2e948941cc3401011cfae54873945f1fe9c292a09d21a64414641426c2d47cad",
        "linux": "ac91e53f985a57fa4c5c196a35fcad91fa187841bee32c1cf684c3d2970096a6",
    },
    "rule-clamp": {
        "win32": "bb95ac638da34430492d5347a6b4d1153685f79197068bc188906d01e23a49b0",
        "linux": "bb95ac638da34430492d5347a6b4d1153685f79197068bc188906d01e23a49b0",
    },
}


def _for_this_platform(hashes: dict[str, str]) -> str:
    """Pick the baseline hash for ``sys.platform``, or skip where none exists.

    A platform with a different maths library has no captured baseline, so
    comparing against another platform's bytes would fail for no real reason.
    """
    if sys.platform not in hashes:
        pytest.skip(f"no c1f3d0a decision-log baseline captured on {sys.platform}")
    return hashes[sys.platform]


@pytest.mark.parametrize(
    ("options", "events", "decisions"),
    [
        (
            {},
            "d8504ab070facdbb2938896fd7b20ecf4559a2970bf304831055c80a70985e07",
            _DECISION_HASHES["exact"],
        ),
        (
            {"with_errors": True},
            "49cbf91a8a72e76c8a0d8d33baa024c866827cc059eabf339b84411af0389869",
            _DECISION_HASHES["prediction-errors"],
        ),
        (
            {"cap": 5},
            "19ec3ffaae634cd5c755a673724f13650b6c01582ef2b81111f8886f99c10d22",
            _DECISION_HASHES["rule-clamp"],
        ),
    ],
    ids=["exact", "prediction-errors", "rule-clamp"],
)
def test_coordinated_logs_match_unoptimized_baseline(
    tmp_path, options, events, decisions
):
    """Retain exact bytes through real transfers, error draws and rule clamping.

    Event logs hold no last-bit costs, so one hash covers every platform and
    is checked before a platform without a decision baseline skips.
    """
    result, _, _ = run(tmp_path, **options)
    assert hashlib.sha256(result.events_path.read_bytes()).hexdigest() == events
    expected_decisions = _for_this_platform(decisions)
    assert (
        hashlib.sha256(result.decisions_path.read_bytes()).hexdigest()
        == expected_decisions
    )


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
