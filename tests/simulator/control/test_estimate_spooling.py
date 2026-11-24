# AI contribution: 50% or more AI-generated
"""Spilling full audits preserves bytes, public records and independent readers."""

import json

from simulator.control.decision_audit import EncodedDecisionRecord, write_decision_log
from simulator.control.estimate_store import EstimateStore


def test_disk_spill_retains_complete_bytes_and_compact_playback(tmp_path):
    """Force disk storage and exercise Unicode offsets and missing projections."""
    originals = [
        EncodedDecisionRecord(json.dumps({"name": "Métro"}, ensure_ascii=False), "{}"),
        EncodedDecisionRecord('{"value":-0.0}'),
    ]
    store = EstimateStore(memory_limit_bytes=1)
    for record in originals:
        store.append(record)
    assert len(store) == 2
    assert list(store) == originals
    assert [r.line for r in store.playback_records()] == ["{}", originals[1].line]
    expected, actual = tmp_path / "original.jsonl", tmp_path / "spooled.jsonl"
    write_decision_log(originals, expected)
    write_decision_log(store, actual)
    assert actual.read_bytes() == expected.read_bytes()


def test_interleaved_reads_do_not_move_each_other_or_the_append_position():
    """A yielded iterator keeps its original view when another caller appends."""
    store = EstimateStore(memory_limit_bytes=1)
    first, second, third = (EncodedDecisionRecord(str(i)) for i in range(3))
    store.append(first)
    store.append(second)
    reader = iter(store)
    assert next(reader) == first
    assert list(store) == [first, second]
    store.append(third)
    assert list(reader) == [second]
    assert list(store) == [first, second, third]
