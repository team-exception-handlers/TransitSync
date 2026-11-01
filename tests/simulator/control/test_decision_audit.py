# AI contribution: 50% or more AI-generated
"""Tests for the decision audit record and log (US-2.2, Task 2.2.4, #44).

Uses the table CDF from ``test_hold_search``: M = 80, s = 60, H = 300 and
weights 1 give J = 0, 4000, 5000, 4500 at L = 200 (hold 20 s) and
J = 0, -4000, -11000, -19500 at L = 1000 (no hold).
"""

import json

import pytest

from simulator.control.break_even import BreakEvenWeights
from simulator.control.decision import DecisionPipeline
from simulator.control.decision_audit import (
    OUTCOME_CHOSEN,
    OUTCOME_LOWER_NET,
    OUTCOME_TIED_LONGER,
    DecisionAuditLog,
    DecisionAuditSource,
    decision_record,
    write_decision_log,
)
from simulator.control.expected_arrivals import TransferEstimate
from simulator.control.hold_search import HoldInputs, HoldSearch, HoldSearchSettings
from simulator.control.strategies.no_control import NoControlStrategy
from simulator.control.walking_cdf import ShiftedExponentialCdf
from simulator.engine.event_log import partial_path

EQUAL = BreakEvenWeights(w_wait=1.0, w_onboard=1.0)
SETTINGS = HoldSearchSettings(step_s=10.0, max_hold_s=30.0)


class TableCdf:
    values = {60.0: 0.25, 70.0: 0.5, 80.0: 0.625, 90.0: 0.6875}

    def cdf(self, t_s):
        return self.values[t_s]


def result_for(load, walking=None):
    inputs = HoldInputs(
        130.0,
        "green_1",
        "mcgill",
        "green",
        load,
        300.0,
        (TransferEstimate("g1", 80, 60.0),),
    )
    return HoldSearch(walking or TableCdf(), EQUAL, SETTINGS).run(inputs)


def outcomes(record):
    return [candidate["outcome"] for candidate in record["candidates"]]


def test_record_holds_the_observation_values_the_decision_used():
    record = decision_record(result_for(load=200))
    assert record["time_s"] == 130.0
    assert record["train_id"] == "green_1"
    assert record["inputs"] == {
        "load": 200,
        "headway_s": 300.0,
        "transfers": [{"group_id": "g1", "group_size": 80, "conn_window_s": 60.0}],
    }
    assert record["weights"] == {"w_wait": 1.0, "w_onboard": 1.0}
    assert record["hold_search"] == {"step_s": 10.0, "max_hold_s": 30.0}


def test_record_holds_the_chosen_duration_and_reason():
    record = decision_record(result_for(load=200))
    assert record["chosen_hold_s"] == 20.0
    assert record["reason"].startswith("hold 20 s:")


def test_record_says_why_each_rejected_candidate_lost():
    record = decision_record(result_for(load=200))
    assert [c["net_ps"] for c in record["candidates"]] == [0.0, 4000.0, 5000.0, 4500.0]
    assert outcomes(record) == [
        OUTCOME_LOWER_NET,
        OUTCOME_LOWER_NET,
        OUTCOME_CHOSEN,
        OUTCOME_LOWER_NET,
    ]


def test_a_decline_is_recorded_with_zero_as_the_decision():
    record = decision_record(result_for(load=1000))
    assert record["chosen_hold_s"] == 0.0
    assert outcomes(record) == [OUTCOME_CHOSEN] + [OUTCOME_LOWER_NET] * 3
    assert [c["worthwhile"] for c in record["candidates"]] == [False] * 4


def test_a_tie_with_a_longer_hold_is_named():
    # L = 300: J(10) = J(20) = 3000, so 20 s loses only for being longer
    record = decision_record(result_for(load=300))
    assert outcomes(record)[1:3] == [OUTCOME_CHOSEN, OUTCOME_TIED_LONGER]


def test_record_names_the_walking_distribution_and_its_parameters():
    walking = ShiftedExponentialCdf(mean_s=300.0, min_s=30.0)
    record = decision_record(result_for(load=200, walking=walking))
    assert record["walking"] == {
        "family": "ShiftedExponentialCdf",
        "mean_s": 300.0,
        "min_s": 30.0,
    }


def test_a_walking_cdf_that_is_not_a_dataclass_is_recorded_by_name():
    record = decision_record(result_for(load=200))
    assert record["walking"] == {"family": "TableCdf"}


def test_a_decision_can_be_recalculated_from_its_record_alone():
    walking = ShiftedExponentialCdf(mean_s=300.0, min_s=30.0)
    record = decision_record(result_for(load=50, walking=walking))
    # Rebuild every number from the record, as a reader of the log would
    rebuilt = HoldSearch(
        ShiftedExponentialCdf(record["walking"]["mean_s"], record["walking"]["min_s"]),
        BreakEvenWeights(**record["weights"]),
        HoldSearchSettings(**record["hold_search"]),
    ).run(
        HoldInputs(
            record["time_s"],
            record["train_id"],
            record["station_id"],
            record["platform_id"],
            record["inputs"]["load"],
            record["inputs"]["headway_s"],
            tuple(TransferEstimate(**g) for g in record["inputs"]["transfers"]),
        )
    )
    assert decision_record(rebuilt) == record


def test_log_collects_records_in_decision_order():
    log = DecisionAuditLog()
    log.record(result_for(load=200))
    log.record(result_for(load=1000))
    assert [r["chosen_hold_s"] for r in log.decision_records()] == [20.0, 0.0]


def test_log_is_a_decision_audit_source():
    assert isinstance(DecisionAuditLog(), DecisionAuditSource)


def test_pipeline_passes_on_the_records_of_an_auditing_strategy():
    class AuditedStrategy(NoControlStrategy):
        def __init__(self):
            self.log = DecisionAuditLog()
            self.log.record(result_for(load=200))

        def decision_records(self):
            return self.log.decision_records()

    pipeline = DecisionPipeline(AuditedStrategy())
    assert len(pipeline.decision_records()) == 1


def test_pipeline_without_an_auditing_strategy_has_no_records():
    assert DecisionPipeline().decision_records() == ()


def test_log_file_is_compact_json_lines_with_a_fixed_key_order(tmp_path):
    path = tmp_path / "decisions.jsonl"
    records = [decision_record(result_for(load=200))]
    write_decision_log(records, path)
    text = path.read_text(encoding="utf-8")
    assert text == json.dumps(records[0], separators=(",", ":")) + "\n"
    assert list(json.loads(text)) == list(records[0])
    assert not partial_path(path).exists()


def test_same_records_give_identical_bytes(tmp_path):
    records = [decision_record(result_for(load=load)) for load in (200, 1000)]
    write_decision_log(records, tmp_path / "first.jsonl")
    write_decision_log(records, tmp_path / "second.jsonl")
    first = (tmp_path / "first.jsonl").read_bytes()
    second = (tmp_path / "second.jsonl").read_bytes()
    assert first == second


def test_log_file_rejects_values_json_cannot_store(tmp_path):
    record = {"time_s": float("nan")}
    path = tmp_path / "decisions.jsonl"
    with pytest.raises(ValueError, match="JSON"):
        write_decision_log([record], path)
    assert not path.exists()
