# AI contribution: 50% or more AI-generated
"""Worker budget, target table and source-drift guard for opt-in measurements.

The timeout only bounds how long a worker may run; assertions keep the wiki and
#411 targets. Every recorded measurement is printed in one table at the end of
the session, passing or failing. Sources are fingerprinted before the first and
after the last measurement, so an edit made during a long run fails the session
instead of silently mislabelling its results.
"""

import math

import pytest

from scripts.benchmark_simulation import source_metadata

_RESULTS = pytest.StashKey[dict]()
_TARGETS = {
    "test_startup": ("run request", 2.0),
    "test_results": ("results after run", 2.0),
    "test_parameters": ("changed parameter", 1.0),
    "test_comparison": ("passenger comparison", 2.0),
    "test_full_day": ("full day", 30.0),
    "test_full_day_results": ("full-day results", 2.0),
}


def pytest_addoption(parser):
    """Let developers allow longer investigations without changing target limits."""
    parser.addoption("--performance-timeout", type=float, default=120.0)


def pytest_configure(config):
    """Start an empty target table for this session."""
    config.stash[_RESULTS] = {}


def pytest_collection_finish(session):
    """Register targets before fixtures run, including those that may time out."""
    rows = session.config.stash[_RESULTS]
    for item in session.items:
        target = _TARGETS.get(getattr(item, "originalname", None))
        if target is None or not hasattr(item, "callspec"):
            continue
        params = item.callspec.params
        strategy = next(
            (params[k] for k in ("strategy", "hourly", "daily") if k in params),
            "unknown",
        )
        rows[item.nodeid] = [*target, strategy, None, "NOT RUN", None]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Keep fixture errors visible without inventing a completed request time."""
    outcome = yield
    report = outcome.get_result()
    row = item.config.stash[_RESULTS].get(item.nodeid)
    if row is None or row[3] is not None:
        return
    if report.failed:
        row[4] = (
            "UNFINISHED" if "Benchmark timed out" in report.longreprtext else "ERROR"
        )
        row[5] = item.config.getoption("--performance-timeout", default=120.0)
    elif report.skipped:
        row[4] = "SKIP"


@pytest.fixture(scope="module")
def performance_timeout_s(request):
    """A positive finite worker budget; the assertions retain wiki targets."""
    value = request.config.getoption("--performance-timeout", default=120.0)
    if not math.isfinite(value) or value <= 0:
        raise pytest.UsageError("--performance-timeout must be finite and positive")
    return value


@pytest.fixture
def record_target(request):
    """Return a recorder for one target row: name, strategy, seconds, limit."""

    def record(target, result, field, limit_s):
        request.config.stash[_RESULTS][request.node.nodeid] = [
            target,
            limit_s,
            result["strategy"],
            result[field],
            "PASS" if result[field] <= limit_s else "FAIL",
            None,
        ]

    return record


@pytest.fixture(scope="session", autouse=True)
def unchanged_sources():
    """Fail the session if tracked or new source files change while it runs."""
    before = source_metadata()["source_sha256"]
    yield
    after = source_metadata()["source_sha256"]
    assert after == before, "source files changed during the performance session"


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Print target, strategy, measured seconds and limit for every row."""
    rows = config.stash.get(_RESULTS, {})
    if not rows:
        return
    terminalreporter.section("performance targets")
    terminalreporter.write_line(
        f"{'target':<22} {'strategy':<22} {'seconds':>9} {'limit':>6}  result"
    )
    for target, limit_s, strategy, seconds, verdict, budget in rows.values():
        measured = f"{seconds:.3f}" if seconds is not None else "unknown"
        detail = f" (worker budget {budget:g} s)" if budget is not None else ""
        terminalreporter.write_line(
            f"{target:<22} {strategy:<22} {measured:>9} {limit_s:>6g}  "
            f"{verdict}{detail}"
        )
