# AI contribution: 50% or more AI-generated
"""Opt-in backend bounds for the Performance wiki's user-facing targets.

No browser runs here: passing a backend bound does not certify display latency.
Every strategy uses the same committed network, date, demand and seed. Timings
are printed before assertions, including when a target fails. No xfail masks
slow strategies. Use -k to select startup, parameters, results, or full_day.
"""

import json

import pytest

from simulator.control.strategies import STRATEGIES
from tests.performance.runner import measured

pytestmark = pytest.mark.performance


@pytest.fixture(scope="module", params=STRATEGIES.names())
def hourly(request, performance_timeout_s):
    """Run once per strategy; startup and results share the same cold response."""
    result = measured(request.param, performance_timeout_s)
    print(json.dumps(result), flush=True)
    return result


def test_startup(hourly):
    """A synchronous backend must finish before its first state can display."""
    assert hourly["request_s"] <= 2.0, hourly


def test_results(hourly):
    """Measure completion through HTTP bytes; browser drawing remains separate."""
    assert hourly["results_s"] <= 2.0, hourly


@pytest.mark.parametrize("strategy", STRATEGIES.names())
def test_parameters(strategy, performance_timeout_s):
    """An uncached changed hold limit must produce its response within 1 s."""
    result = measured(strategy, performance_timeout_s, changed=True)
    print(json.dumps(result), flush=True)
    assert result["request_s"] <= 1.0, result


@pytest.fixture(scope="module", params=STRATEGIES.names())
def daily(request, performance_timeout_s):
    """Share a full-day response between its total and post-completion checks."""
    result = measured(request.param, performance_timeout_s, full_day=True)
    print(json.dumps(result), flush=True)
    return result


def test_full_day(daily):
    """Include the complete service day without adding a run-length API field."""
    assert daily["duration_s"] >= 86400, daily
    assert daily["request_s"] <= 30.0, daily


def test_full_day_results(daily):
    """The results phase must also meet its target after a long simulation."""
    assert daily["results_s"] <= 2.0, daily
