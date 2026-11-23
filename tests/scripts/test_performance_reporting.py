# AI contribution: 50% or more AI-generated
"""The actual performance plugin reports failed fixtures without timed runs."""

import os
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]


@pytest.fixture
def reporting(pytester, monkeypatch):
    """Load the real hooks, replacing only source discovery in the isolated repo."""
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv(
        "PYTHONPATH", str(root) + os.pathsep + os.environ.get("PYTHONPATH", "")
    )
    source = (root / "tests/performance/conftest.py").read_text()
    pytester.makeconftest(
        source + '\ndef source_metadata():\n    return {"source_sha256": "fixed"}\n'
    )
    return pytester


def test_shared_fixture_timeouts_keep_all_dependent_target_rows(reporting):
    """Unknown completion time stays unknown for both hourly targets."""
    reporting.makepyfile("""
import pytest
@pytest.fixture(params=["rolling_horizon"])
def hourly(request):
    pytest.fail("Benchmark timed out; API completion time is unknown")
def test_startup(hourly, record_target):
    raise AssertionError("fixture must fail first")
def test_results(hourly, record_target):
    raise AssertionError("fixture must fail first")
""")
    result = reporting.runpytest_subprocess("-q", "--performance-timeout=300")
    result.assert_outcomes(errors=2)
    result.stdout.fnmatch_lines(
        [
            "*run request*rolling_horizon*unknown*2*UNFINISHED*300*",
            "*results after run*rolling_horizon*unknown*2*UNFINISHED*300*",
        ]
    )


def test_successful_targets_keep_actual_times_and_pass_fail_status(reporting):
    """A failed threshold must retain its measured time, not become an error."""
    reporting.makepyfile("""
import pytest
@pytest.mark.parametrize("strategy", ["no_control"])
def test_parameters(strategy, record_target):
    result = {"strategy":strategy, "request_s":1.5}
    record_target("changed parameter", result, "request_s", 1)
    assert 1.5 <= 1
""")
    result = reporting.runpytest_subprocess("-q")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*changed parameter*no_control*1.500*1*FAIL"])
