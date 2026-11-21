# AI contribution: 50% or more AI-generated
"""Independent execution budget for opt-in performance measurements."""

import math

import pytest


def pytest_addoption(parser):
    """Let developers allow longer investigations without changing target limits."""
    parser.addoption("--performance-timeout", type=float, default=120.0)


@pytest.fixture(scope="module")
def performance_timeout_s(request):
    """A positive finite worker budget; the assertions retain wiki targets."""
    value = request.config.getoption("--performance-timeout", default=120.0)
    if not math.isfinite(value) or value <= 0:
        raise pytest.UsageError("--performance-timeout must be finite and positive")
    return value
