# AI contribution: 50% or more AI-generated
"""Tests for the event log writer and run summary (US-1.1, Task 1.1.6, #99)."""

import json

import pytest

from simulator.engine.event_log import (
    SUMMARY_SCHEMA_VERSION,
    EventLogWriter,
    RunSummary,
    encode_record,
    write_summary,
)
from simulator.engine.events import SCHEMA_VERSION, EventType, PassengerArrival


def _arrival(time_s, passenger_id="p-1"):
    return PassengerArrival(
        time_s=time_s, passenger_id=passenger_id, group_id="g-1", platform_id="p"
    )


def test_record_is_one_compact_line_in_schema_key_order():
    assert encode_record(_arrival(12)) == (
        f'{{"schema_version":{SCHEMA_VERSION},"event_type":"passenger_arrival",'
        '"time_s":12.0,"passenger_id":"p-1","group_id":"g-1","platform_id":"p"}'
    )


def test_writer_renames_the_log_only_when_finished(tmp_path):
    path = tmp_path / "events.jsonl"
    with EventLogWriter(path) as writer:
        writer.write(_arrival(1.0, "p-1"))
        writer.write(_arrival(2.0, "p-2"))
        assert not path.exists()
    lines = path.read_bytes().split(b"\n")
    # Two records and the empty string after the final newline
    assert len(lines) == 3
    assert lines[-1] == b""
    assert b"\r" not in path.read_bytes()


def test_writer_keeps_only_a_partial_log_when_the_run_fails(tmp_path):
    path = tmp_path / "events.jsonl"
    with pytest.raises(KeyError), EventLogWriter(path) as writer:
        writer.write(_arrival(1.0))
        raise KeyError("component failed")
    assert not path.exists()
    assert (tmp_path / "events.jsonl.partial").exists()


def test_writing_outside_the_context_is_rejected(tmp_path):
    writer = EventLogWriter(tmp_path / "events.jsonl")
    with pytest.raises(RuntimeError, match="outside its context"):
        writer.write(_arrival(1.0))


def test_summary_counts_events_and_lists_every_type():
    summary = RunSummary(master_seed=7, duration_s=60.0)
    summary.record(_arrival(5.0, "p-1"))
    summary.record(_arrival(9.5, "p-2"))
    result = summary.to_dict()
    assert result["events_processed"] == 2
    assert result["end_time_s"] == 9.5
    assert result["events_by_type"] == {
        event_type.value: (2 if event_type is EventType.PASSENGER_ARRIVAL else 0)
        for event_type in EventType
    }


def test_empty_summary_has_zero_counts(tmp_path):
    path = tmp_path / "summary.json"
    write_summary(RunSummary(master_seed=0, duration_s=0.0), path)
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert written["events_processed"] == 0
    assert written["end_time_s"] == 0.0
    assert set(written["events_by_type"].values()) == {0}
    assert written["skipped_event_types"] == []


def test_summary_lists_skipped_event_types_in_stable_order():
    summary = RunSummary(
        master_seed=0,
        duration_s=60.0,
        skipped_event_types=frozenset(
            {EventType.MISSED_CONNECTION, EventType.ALIGHTING}
        ),
    )
    assert summary.to_dict()["skipped_event_types"] == [
        "alighting",
        "missed_connection",
    ]
