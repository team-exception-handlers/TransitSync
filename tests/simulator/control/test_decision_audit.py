# AI contribution: 50% or more AI-generated
"""Tests for the decision audit record and log (US-2.2, Task 2.2.4, #44).

Uses the table CDF from ``test_hold_search``: M = 80, s = 60, H = 300 and
weights 1 give J = 0, 4000, 5000, 4500 at L = 200 (hold 20 s) and
J = 0, -4000, -11000, -19500 at L = 1000 (no hold).
"""

import json
import math

import pytest

from simulator.control.break_even import BreakEvenWeights
from simulator.control.decision import DecisionPipeline
from simulator.control.decision_audit import (
    DECISION_SCHEMA_VERSION,
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
from simulator.control.interface import (
    CurrentVisitState,
    ObservationSnapshot,
    PlatformState,
)
from simulator.control.strategies.no_control import NoControlStrategy
from simulator.control.walking_cdf import ShiftedExponentialCdf
from simulator.engine.event_log import partial_path
from simulator.engine.events import SCHEMA_VERSION
from simulator.trains.suspension import LineSuspension

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
    context = ObservationSnapshot(
        100,
        "green_1",
        "mcgill",
        "green",
        100,
        (),
        (PlatformState("rem", 0, 20), PlatformState("green", 0, 50)),
        (),
        current_visit=CurrentVisitState("green", True),
        suspensions=(LineSuspension("green", 100, 140),),
        minimum_gap_s=100,
    )
    inputs = HoldInputs(
        100, "green_1", "mcgill", "green", 50, 300, (TransferEstimate("g1", 80, 100),)
    )
    result = HoldSearch(
        ShiftedExponentialCdf(300, 30), EQUAL, HoldSearchSettings(10, 60)
    ).run(inputs, departure_context=context)
    record = json.loads(json.dumps(decision_record(result)))
    assert DECISION_SCHEMA_VERSION == record["schema_version"] == 3
    assert SCHEMA_VERSION == 4
    assert record["time_s"] == 100
    assert record["no_hold_departure_s"] == 150
    assert record["departure_context"] == {
        "line_id": "green",
        "is_trip_origin": True,
        "previous_departure_s": 50,
        "minimum_gap_s": 100,
        "suspensions": [{"line_id": "green", "start_s": 100, "end_s": 140}],
    }
    # Dispatch resumes at 140 s; green's previous departure + gap is
    # 50 + 100 = 150 s, so the train must wait until 150 s without a hold.
    for candidate in record["candidates"]:
        departure = max(150, record["time_s"] + candidate["hold_s"])
        delta = departure - 150
        # The feeder arrives at 0; F(x)=1-exp(-(x-30)/270). Count walkers
        # arriving after 150 s and by the departure with a hold.
        caught = 80 * (math.exp(-120 / 270) - math.exp(-(departure - 30) / 270))
        assert candidate["departure_s"] == departure
        assert candidate["incremental_delay_s"] == delta
        assert candidate["n_caught"] == pytest.approx(caught, abs=1e-9, rel=0)
        assert candidate["benefit_ps"] == pytest.approx(caught * 300, abs=1e-6, rel=0)
        assert candidate["cost_ps"] == 50 * delta
        assert candidate["net_ps"] == pytest.approx(
            caught * 300 - 50 * delta, abs=1e-6, rel=0
        )


def test_log_collects_records_in_decision_order():
    log = DecisionAuditLog()
    log.record(result_for(load=200))
    log.record(result_for(load=1000))
    assert [r["chosen_hold_s"] for r in log.decision_records()] == [20.0, 0.0]


def test_changing_a_returned_record_leaves_the_stored_record_unchanged():
    log = DecisionAuditLog()
    log.record(result_for(load=400))
    returned = log.decision_records()[0]
    returned["inputs"]["load"] = 999
    returned["candidates"][0]["net_ps"] = -1.0
    stored = log.decision_records()[0]
    assert stored["inputs"]["load"] == 400
    assert stored["candidates"][0]["net_ps"] == 0.0


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
