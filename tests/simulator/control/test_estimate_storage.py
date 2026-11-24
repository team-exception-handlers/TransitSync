# AI contribution: 50% or more AI-generated
"""Encoded estimates preserve byte order and public audit isolation.

The optimized representation is private: callers still receive mutable JSON
containers they own. Check exact log bytes independently of decoded equality,
including nulls, floating values and the existing invalid-number rejection.
"""

import json
from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulator.control.decision_audit import (
    EstimateEncoder,
    encode_decision_record,
    estimates_record,
    write_decision_log,
)
from tests.simulator.control.test_estimates_audit import run_with_kappa
from tests.simulator.control.test_prediction_error import snapshot


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


@given(
    st.text(),
    st.one_of(st.none(), st.floats(allow_nan=False, allow_infinity=False)),
    st.integers(min_value=-(2**100), max_value=2**100),
)
@settings(max_examples=50)
def test_prepared_encoder_retains_all_bytes_and_compact_view(name, arrival, load):
    """Unicode escaping, signed zero, exponents and large integers stay exact."""
    truth = snapshot()
    first = replace(
        truth.trains[0], train_id=name, predicted_arrival_s=arrival, onboard_load=load
    )
    truth = replace(truth, trains=(first, *truth.trains[1:]), train_id=name)
    record = estimates_record(truth, truth)
    actual = EstimateEncoder().encode(truth, truth)
    assert actual.line == encode_decision_record(record).line
    record["trains"] = [r for r in record["trains"] if r["train_id"] == name]
    assert actual.decision_line == encode_decision_record(record).line


@pytest.mark.parametrize("arrival", [float("nan"), float("inf"), -float("inf")])
def test_compact_view_never_hides_invalid_unshown_train_values(arrival):
    """Every full audit field is validated even when playback omits that train."""
    truth = snapshot()
    bad = replace(truth.trains[1], predicted_arrival_s=arrival)
    truth = replace(truth, trains=(truth.trains[0], bad))
    encoder = EstimateEncoder()
    with pytest.raises(ValueError):
        encoder.encode(truth, truth)
