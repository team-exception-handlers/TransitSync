# AI contribution: 50% or more AI-generated
"""Streaming audit adaptation keeps the previous playback contract intact.

One-shot records must serve both estimates and switches without losing the
second record kind, changing stable sorting, or swallowing corrupt JSON.
"""

import json
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from api.simulation_run import _iter_json_lines, _playback_audit_lines
from api.station_view import _estimate_records, _mode_switch_records, _playback_audit
from tests.api.test_station_view import SHOWN, _estimates, _switch


def test_single_pass_audit_matches_sequence_adapter():
    """Estimates and unsorted switches both survive a one-shot input iterator."""
    records = [
        _switch(900.0, "rem_mcgill_0", "connection_protection"),
        _estimates(120.0, "T1", "green_mcgill_0"),
        _switch(420.0, "rem_mcgill_0", "headway_regulation"),
        _estimates(240.0, "T2", "green_mcgill_0"),
    ]
    decisions = [{"time_s": 120.0, "train_id": "T1", "platform_id": "green_mcgill_0"}]
    switches, estimates = _playback_audit(iter(records), decisions, SHOWN)
    assert switches == _mode_switch_records(records, SHOWN)
    assert estimates == _estimate_records(records, decisions)
    assert _playback_audit(iter(()), [], SHOWN) == ([], [])


def test_log_reader_defers_decode_errors_until_the_bad_record(tmp_path):
    """Read valid lines lazily and propagate corruption instead of hiding it."""
    path = tmp_path / "decisions.jsonl"
    path.write_text('{"kind":"estimates"}\ninvalid\n', encoding="utf-8")
    records = _iter_json_lines(path)
    assert next(records) == {"kind": "estimates"}
    with pytest.raises(json.JSONDecodeError):
        next(records)


@given(
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(),
    st.integers(min_value=-(2**100), max_value=2**100),
)
@settings(max_examples=50)
def test_native_log_decoding_matches_stdlib_json(tmp_path_factory, value, text, count):
    """Keep float signs, large integers and escaped Unicode exactly equivalent."""
    record = {"time_s": value, "train_id": text, "count": count, "other": None}
    path = tmp_path_factory.mktemp("audit-json") / "decisions.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    [decoded] = _iter_json_lines(path)
    assert json.dumps(decoded) == json.dumps(record)


def test_reader_retains_stdlib_support_for_unpaired_surrogates(tmp_path):
    """The native fast path may reject a legacy JSON string; fallback retains it."""
    record = {"train_id": "\ud800"}
    path = tmp_path / "decisions.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    assert list(_iter_json_lines(path)) == [record]


def test_header_filter_retains_the_same_playback_audit(tmp_path):
    """Unshown estimate bodies can be omitted without changing adapter output."""
    records = [
        _estimates(120.0, "T1", "green_mcgill_0"),
        _estimates(240.0, "T2", "green_mcgill_0"),
        _switch(420.0, "rem_mcgill_0", "headway_regulation"),
    ]
    decisions = [{"time_s": 120.0, "train_id": "T1", "platform_id": "green_mcgill_0"}]
    events = [{"event_type": "hold", **decisions[0]}]
    connection = SimpleNamespace(
        from_platform_id="rem_mcgill_0", to_platform_id="green_mcgill_0"
    )
    path = tmp_path / "decisions.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    streamed = _playback_audit_lines(path, events, connection)
    assert _playback_audit(streamed, decisions, SHOWN) == _playback_audit(
        records, decisions, SHOWN
    )


def test_unshown_estimate_body_still_rejects_corrupt_json(tmp_path):
    """Ignoring an unused body must not hide event-log corruption."""
    path = tmp_path / "decisions.jsonl"
    path.write_text('{"kind":"estimates","trains":[invalid]}\n', encoding="utf-8")
    connection = SimpleNamespace(from_platform_id="rem", to_platform_id="metro")
    records = _playback_audit_lines(path, [], connection)
    with pytest.raises(json.JSONDecodeError):
        next(records)
