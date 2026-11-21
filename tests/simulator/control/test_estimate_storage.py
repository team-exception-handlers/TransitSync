# AI contribution: 50% or more AI-generated
"""Encoded estimates preserve byte order and public audit isolation.

The optimized representation is private: callers still receive mutable JSON
containers they own. Check exact log bytes independently of decoded equality,
including nulls, floating values and the existing invalid-number rejection.
"""

import json

import pytest

from simulator.control.decision_audit import encode_decision_record, write_decision_log
from tests.simulator.control.test_estimates_audit import run_with_kappa


def test_encoded_estimates_match_the_original_json_bytes(tmp_path):
    """Nulls, floating timestamps and insertion order retain the log schema."""
    record = {
        "kind": "estimates",
        "time_s": 120.0,
        "trains": [
            {"train_id": "A", "predicted_arrival_s": {"seen": None, "true": 130.0}}
        ],
        "transfers": [],
    }
    encoded = encode_decision_record(record)
    assert encoded.line == json.dumps(record, separators=(",", ":"), allow_nan=False)
    plain = tmp_path / "plain.jsonl"
    cached = tmp_path / "cached.jsonl"
    write_decision_log([record], plain)
    write_decision_log([encoded], cached)
    assert plain.read_bytes() == cached.read_bytes()
    bad = {"time_s": float("nan")}
    with pytest.raises(ValueError):
        encode_decision_record(bad)


def test_public_estimate_readers_remain_detached(tmp_path):
    """Encoded storage cannot be mutated through either public reader."""
    pipeline, expected = run_with_kappa(tmp_path, 1.0)
    records = pipeline.iter_decision_records()
    first = next(records)
    first["trains"][0]["onboard_load"]["seen"] = -1
    assert pipeline.decision_records() == tuple(expected)
    again = pipeline.decision_records()
    again[0]["trains"].clear()
    assert pipeline.decision_records() == tuple(expected)
