# AI contribution: 50% or more AI-generated
"""Every strategy's API response stays byte-identical to a saved reference (#412).

The references in ``fixtures/response_baseline`` were captured from ``main`` at
commit 3976031, before any #412 performance change, on Windows (CPython 3.13)
and Linux (``python:3.12-slim``). Both platforms produced identical bodies, and
each case was run twice to confirm it repeats exactly.

Never regenerate these files from optimized code: that would only compare the
optimization with itself. A change that alters responses on purpose needs a
new reference captured from its unoptimized parent and reviewed on its own.

Cases:
- 600-second runs: six strategies at all three interchanges (SHA-256 only)
- McGill one-hour default scenario: the five non-Coordinated strategies, with
  full gzipped bodies so a failure shows which fields changed
- Coordinated at McGill for 900 seconds, also with a full body

Coordinated cases carry the opt-in ``reference`` marker. Until the compiled
search lands, a single 600-second Coordinated run takes minutes. Run them
with ``pytest -m reference tests/api/test_response_baseline.py``.
"""

import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.simulation_run as simulation_run
from api.main import create_app

FIXTURES = Path(__file__).parent / "fixtures" / "response_baseline"

# The request every reference used. Adaptive also needs its threshold.
MAX_HOLD_S = 300
IRREGULARITY_THRESHOLD = 0.2


def _cases() -> list[pytest.param]:
    """Read the manifest; one parameter per captured response."""
    lines = (FIXTURES / "responses.jsonl").read_text(encoding="utf-8").splitlines()
    cases = []
    for case in map(json.loads, lines):
        duration = case["duration_s"] or "hour"
        marks = [pytest.mark.reference] if case["strategy"] == "rolling_horizon" else []
        name = f"{case['connection_id']}-{case['strategy']}-{duration}"
        cases.append(pytest.param(case, marks=marks, id=name))
    return cases


def _request(connection_id: str, strategy: str) -> dict[str, object]:
    """Build the same request body the capture script sent."""
    body: dict[str, object] = {
        "connection_id": connection_id,
        "strategy": strategy,
        "max_hold_time": MAX_HOLD_S,
    }
    if strategy == "adaptive":
        body["irregularity_threshold"] = IRREGULARITY_THRESHOLD
    return body


@pytest.mark.parametrize("case", _cases())
def test_response_matches_the_reference_captured_from_main(case, monkeypatch):
    """Compare the full response, not just selected fields."""
    duration_s = case["duration_s"]
    if duration_s is not None:
        # Shorten only the scenario length; network, seeds and events are unchanged
        original = simulation_run.SimulationRunService._load_scenario

        def load(service, *args, **kwargs):
            return replace(original(service, *args, **kwargs), duration_s=duration_s)

        monkeypatch.setattr(simulation_run.SimulationRunService, "_load_scenario", load)

    with TestClient(create_app()) as client:
        response = client.post(
            "/simulation/run", json=_request(case["connection_id"], case["strategy"])
        )
    response.raise_for_status()

    if case["body"] is not None:
        expected = gzip.decompress((FIXTURES / case["body"]).read_bytes())
        # Parsed comparison first, so pytest reports the differing fields
        assert json.loads(response.content) == json.loads(expected)
        assert response.content == expected
    assert hashlib.sha256(response.content).hexdigest() == case["sha256"]
