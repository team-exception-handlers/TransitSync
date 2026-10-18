# AI contribution: 50% or more AI-generated
"""Tests for the simulation runner (US-1.1, Task 1.1.6, #99).

Uses the tiny network from ``tests/conftest.py``. Hand-worked timeline of the
tiny timetable with no control strategy. The departure becomes due at
arrival + dwell, and with no hold the train leaves at that same instant:

    green-1  arrives 100, dwell 20 -> due and departs 120
    rem-1    arrives 120, dwell 30 -> due and departs 150
    green-2  arrives 280, dwell 20 -> due and departs 300

At 120 s, rem-1 arriving comes before green-1's departure because arrivals are
earlier in the documented tie order, and departure due comes before departure.
"""

import json
from dataclasses import replace

import pytest

from simulator.engine import runner
from simulator.engine.event_log import EVENTS_FILE, SUMMARY_FILE
from simulator.engine.events import Boarding, PassengerArrival
from simulator.engine.runner import RunError, run_scenario

EXPECTED_TIMELINE = [
    ("train_arrival", "green-1", 100.0),
    ("train_arrival", "rem-1", 120.0),
    ("departure_due", "green-1", 120.0),
    ("train_departure", "green-1", 120.0),
    ("departure_due", "rem-1", 150.0),
    ("train_departure", "rem-1", 150.0),
    ("train_arrival", "green-2", 280.0),
    ("departure_due", "green-2", 300.0),
    ("train_departure", "green-2", 300.0),
]


def _read_log(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _timeline(records):
    return [(r["event_type"], r["train_id"], r["time_s"]) for r in records]


def _output_files(folder):
    return sorted(path.name for path in folder.iterdir())


class TransferPassengers:
    """Transferring passengers who reach a platform and board one train.

    Stands in for passenger logic (US-1.3): each passenger arrives at a given
    time and boards ``train_id`` at that same instant.
    """

    def __init__(self, train_id, platform_id, arrival_times_s):
        self._train_id = train_id
        self._platform_id = platform_id
        self._arrival_times_s = arrival_times_s

    def start(self, scheduler):
        for index, time_s in enumerate(self._arrival_times_s):
            scheduler.schedule(
                PassengerArrival(
                    time_s=time_s,
                    passenger_id=f"p-{index}",
                    group_id="g-1",
                    platform_id=self._platform_id,
                )
            )

    def handle(self, event, scheduler):
        if isinstance(event, PassengerArrival):
            scheduler.schedule(
                Boarding(
                    time_s=event.time_s,
                    passenger_id=event.passenger_id,
                    train_id=self._train_id,
                    platform_id=self._platform_id,
                )
            )


REM_PLATFORM = "STA_ZCD_BT_QUAI_01_MCG"


def _with_passengers(held_rem_component, arrival_times_s):
    """Held rem-1 plus passengers who board it at the given times."""

    def build(_scenario, _streams):
        passengers = TransferPassengers("rem-1", REM_PLATFORM, arrival_times_s)
        return [held_rem_component, passengers]

    return build


def test_smoke_run_with_no_control_strategy_writes_the_expected_log(
    tmp_path, minimal_scenario, build_streams, build_tiny_network
):
    result = run_scenario(minimal_scenario, build_streams, build_tiny_network, tmp_path)
    assert result.events_path == tmp_path / EVENTS_FILE
    assert _timeline(_read_log(result.events_path)) == EXPECTED_TIMELINE


def test_summary_matches_the_hand_count(
    tmp_path, minimal_scenario, build_streams, build_tiny_network
):
    result = run_scenario(minimal_scenario, build_streams, build_tiny_network, tmp_path)
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["master_seed"] == minimal_scenario.master_seed
    assert summary["duration_s"] == 600.0
    assert summary["events_processed"] == 9
    assert summary["events_pending"] == 0
    assert summary["end_time_s"] == 300.0
    assert summary["events_by_type"]["train_arrival"] == 3
    assert summary["events_by_type"]["departure_due"] == 3
    assert summary["events_by_type"]["train_departure"] == 3
    assert summary["events_by_type"]["hold"] == 0


def test_same_scenario_and_seed_give_byte_identical_output(
    tmp_path, minimal_scenario, build_streams, build_tiny_network
):
    first = run_scenario(
        minimal_scenario, build_streams, build_tiny_network, tmp_path / "first"
    )
    second = run_scenario(
        minimal_scenario, build_streams, build_tiny_network, tmp_path / "second"
    )
    # Full files, not summary metrics (US-1.1 acceptance criteria)
    assert first.events_path.read_bytes() == second.events_path.read_bytes()
    assert first.summary_path.read_bytes() == second.summary_path.read_bytes()


def test_streams_are_built_from_the_master_seed_and_passed_to_components(
    tmp_path, minimal_scenario, build_streams, build_tiny_network
):
    seen = {}

    def spy_components(scenario, streams):
        seen["streams"] = streams
        return build_tiny_network(scenario, streams)

    run_scenario(minimal_scenario, build_streams, spy_components, tmp_path)
    assert seen["streams"].master_seed == minimal_scenario.master_seed


def test_period_ending_mid_dwell_leaves_the_departure_pending(
    tmp_path, minimal_scenario, build_streams, build_tiny_network
):
    # Ends at 290 s: green-2 has arrived (280) but its departure is only due
    # at 300, so that event is still waiting
    scenario = replace(minimal_scenario, duration_s=290.0)
    result = run_scenario(scenario, build_streams, build_tiny_network, tmp_path)
    assert _timeline(_read_log(result.events_path)) == EXPECTED_TIMELINE[:7]
    assert result.summary.events_pending == 1
    assert result.summary.end_time_s == 280.0


def test_period_ending_before_the_first_event_processes_nothing(
    tmp_path, minimal_scenario, build_streams, build_tiny_network
):
    scenario = replace(minimal_scenario, duration_s=50.0)
    result = run_scenario(scenario, build_streams, build_tiny_network, tmp_path)
    assert result.events_path.read_bytes() == b""
    assert result.summary.events_processed == 0
    # The three scheduled arrivals are still waiting
    assert result.summary.events_pending == 3


def test_run_with_no_components_writes_an_empty_log(
    tmp_path, minimal_scenario, build_streams
):
    result = run_scenario(minimal_scenario, build_streams, lambda _s, _r: [], tmp_path)
    assert result.events_path.read_bytes() == b""
    assert json.loads(result.summary_path.read_text())["events_processed"] == 0


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("duration_s", -1.0, "duration_s"),
        ("duration_s", float("nan"), "duration_s"),
        ("duration_s", "600", "duration_s"),
        ("master_seed", -5, "master_seed"),
        ("master_seed", 1.5, "master_seed"),
    ],
)
def test_invalid_scenario_is_rejected_before_any_file_is_written(
    tmp_path,
    minimal_scenario,
    build_streams,
    build_tiny_network,
    field,
    value,
    message,
):
    scenario = replace(minimal_scenario, **{field: value})
    output_dir = tmp_path / "out"
    with pytest.raises(ValueError, match=message):
        run_scenario(scenario, build_streams, build_tiny_network, output_dir)
    assert not output_dir.exists()


def test_unwritable_output_folder_raises_a_run_error(
    tmp_path, minimal_scenario, build_streams, build_tiny_network
):
    # A file where the output folder should be makes mkdir fail
    blocked = tmp_path / "out"
    blocked.write_text("not a folder")
    with pytest.raises(RunError, match="could not write run output"):
        run_scenario(minimal_scenario, build_streams, build_tiny_network, blocked)


def test_failing_component_leaves_no_complete_log(
    tmp_path, minimal_scenario, build_streams, build_tiny_network
):
    class FailingComponent:
        def start(self, scheduler):
            pass

        def handle(self, event, scheduler):
            raise RuntimeError("component failed")

    def build(scenario, streams):
        return [*build_tiny_network(scenario, streams), FailingComponent()]

    with pytest.raises(RuntimeError, match="component failed"):
        run_scenario(minimal_scenario, build_streams, build, tmp_path)
    # Not even the partial log is left behind
    assert _output_files(tmp_path) == []


def test_passenger_boarding_during_a_hold_is_counted_on_the_departure(
    tmp_path, minimal_scenario, build_streams, held_rem_component
):
    # One passenger boards during the dwell (140), one during the hold (170).
    # The departure is created at 190, when the hold ends, so both count.
    build = _with_passengers(held_rem_component, (140.0, 170.0))
    result = run_scenario(minimal_scenario, build_streams, build, tmp_path)
    records = _read_log(result.events_path)
    assert [(r["event_type"], r["time_s"]) for r in records] == [
        ("train_arrival", 120.0),
        ("passenger_arrival", 140.0),
        ("boarding", 140.0),
        ("departure_due", 150.0),
        ("hold", 150.0),
        ("passenger_arrival", 170.0),
        ("boarding", 170.0),
        ("hold_end", 190.0),
        ("train_departure", 190.0),
    ]
    departure = records[-1]
    assert departure["hold_s"] == 40.0
    assert departure["scheduled_s"] == 150.0
    assert departure["boarded_count"] == 2
    assert departure["alighted_count"] == 0
    assert departure["onboard_load"] == 2


def test_passenger_arriving_exactly_as_the_hold_ends_still_boards(
    tmp_path, minimal_scenario, build_streams, held_rem_component
):
    # Boundary: boarding at 190 comes before hold_end and train_departure at
    # 190 in the tie order, so the passenger is on the departing train
    build = _with_passengers(held_rem_component, (190.0,))
    result = run_scenario(minimal_scenario, build_streams, build, tmp_path)
    records = _read_log(result.events_path)
    assert [r["event_type"] for r in records[-4:]] == [
        "passenger_arrival",
        "boarding",
        "hold_end",
        "train_departure",
    ]
    assert records[-1]["boarded_count"] == 1
    assert records[-1]["onboard_load"] == 1


def test_rerun_into_a_folder_with_previous_output_is_rejected_and_keeps_it(
    tmp_path, minimal_scenario, build_streams, build_tiny_network
):
    first = run_scenario(minimal_scenario, build_streams, build_tiny_network, tmp_path)
    events_before = first.events_path.read_bytes()
    summary_before = first.summary_path.read_bytes()

    with pytest.raises(RunError, match="already contains run output"):
        run_scenario(minimal_scenario, build_streams, build_tiny_network, tmp_path)
    # The earlier run's files are untouched and nothing new was added
    assert first.events_path.read_bytes() == events_before
    assert first.summary_path.read_bytes() == summary_before
    assert _output_files(tmp_path) == [EVENTS_FILE, SUMMARY_FILE]


@pytest.mark.parametrize("leftover", [EVENTS_FILE, SUMMARY_FILE])
def test_folder_with_either_output_file_is_rejected_naming_it(
    tmp_path, minimal_scenario, build_streams, build_tiny_network, leftover
):
    (tmp_path / leftover).write_text("from an older run")
    with pytest.raises(RunError, match=leftover):
        run_scenario(minimal_scenario, build_streams, build_tiny_network, tmp_path)
    assert _output_files(tmp_path) == [leftover]


def test_existing_folder_with_unrelated_files_is_accepted(
    tmp_path, minimal_scenario, build_streams, build_tiny_network
):
    (tmp_path / "notes.txt").write_text("not run output")
    run_scenario(minimal_scenario, build_streams, build_tiny_network, tmp_path)
    assert _output_files(tmp_path) == [EVENTS_FILE, "notes.txt", SUMMARY_FILE]


def test_failed_summary_write_leaves_no_output(
    tmp_path, minimal_scenario, build_streams, build_tiny_network, monkeypatch
):
    # The event log is complete by then, but without its summary it must not
    # be left behind on its own
    def failing_write(_summary, _path):
        raise OSError("disk full")

    monkeypatch.setattr(runner, "write_summary", failing_write)
    with pytest.raises(RunError, match="could not write run output"):
        run_scenario(minimal_scenario, build_streams, build_tiny_network, tmp_path)
    assert _output_files(tmp_path) == []
