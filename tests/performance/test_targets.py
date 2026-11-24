# AI contribution: 50% or more AI-generated
"""Opt-in backend bounds for the #411 targets and the Performance wiki.

No browser runs here: passing a backend bound does not certify display latency.
Every strategy uses the same committed network, date, demand and seed, and each
measurement runs in a fresh process with a fresh application, so no result-cache
hit is counted. Timings are printed before assertions and summarized in a table
at the end of the session, including failures. No xfail masks slow strategies.

#411 targets: first ``/simulation/run`` response within 2 s, a changed parameter
(maximum hold 300 -> 120 s) within 1 s, the entire uncached
``/simulation/passenger-comparison`` request within 2 s, and a full service day
within 30 s. ``results_s`` (simulator return through HTTP bytes) is the wiki's
"results after completion" measure and is kept as a supplementary check.
Use -k to select startup, parameters, comparison, results or full_day.
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


def test_startup(hourly, record_target):
    """A synchronous backend must finish before its first state can display."""
    record_target("run request", hourly, "request_s", 2.0)
    assert hourly["request_s"] <= 2.0, hourly


def test_results(hourly, record_target):
    """Supplementary: preparation after the simulator returns, through HTTP bytes."""
    record_target("results after run", hourly, "results_s", 2.0)
    assert hourly["results_s"] <= 2.0, hourly


@pytest.mark.parametrize("strategy", STRATEGIES.names())
def test_parameters(strategy, performance_timeout_s, record_target):
    """An uncached changed hold limit must produce its response within 1 s."""
    result = measured(strategy, performance_timeout_s, changed=True)
    print(json.dumps(result), flush=True)
    record_target("changed parameter", result, "request_s", 1.0)
    assert result["request_s"] <= 1.0, result


@pytest.mark.parametrize("strategy", STRATEGIES.names())
def test_comparison(strategy, performance_timeout_s, record_target):
    """The whole uncached passenger-comparison request, both runs included."""
    result = measured(strategy, performance_timeout_s, compare=True)
    print(json.dumps(result), flush=True)
    record_target("passenger comparison", result, "request_s", 2.0)
    assert result["request_s"] <= 2.0, result


@pytest.fixture(scope="module", params=STRATEGIES.names())
def daily(request, performance_timeout_s):
    """Share a full-day response between its total and post-completion checks."""
    result = measured(request.param, performance_timeout_s, full_day=True)
    print(json.dumps(result), flush=True)
    return result


def test_full_day(daily, record_target):
    """Include the complete service day without adding a run-length API field."""
    record_target("full day", daily, "request_s", 30.0)
    assert daily["duration_s"] >= 86400, daily
    assert daily["request_s"] <= 30.0, daily


def test_full_day_results(daily, record_target):
    """Supplementary: the results phase after a long simulation."""
    record_target("full-day results", daily, "results_s", 2.0)
    assert daily["results_s"] <= 2.0, daily
