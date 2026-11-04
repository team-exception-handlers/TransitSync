# AI contribution: 50% or more AI-generated
"""Compare three ways to decide when trains should leave (#48).

Use the same timetable, starting delays and seed for each run.
Work out the expected times by hand, in seconds.
The engine keeps trains apart: see Mathematical Foundations (Section 6).

These tests use fixed times, with no random choices.
Other tests check random inputs.
Whole seconds let us compare times exactly.
Work out hold times without using the code being tested.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from simulator.engine.runner import RunResult
from simulator.trains.suspension import LineSuspension
from simulator.trains.train import ScheduledStop, Train
from tests.simulator.control.headway_run_helpers import (
    event_tuples,
    run_selected,
    scenario_input,
)

MOVEMENT = ("train_id", "platform_id", "time_s")


def train(
    train_id: str,
    arrival: float,
    departure: float,
    *,
    platform: str = "P",
    delay: float = 0,
) -> Train:
    """Create a fresh train visit with an initial delay in seconds.

    Negative delay means early; keep the original timetable.
    Set the line so dispatch suspensions can apply.
    """
    return Train(
        train_id,
        800,
        (ScheduledStop("S", platform, arrival, departure),),
        current_delay=delay,
        line_id="green",
    )


def comparison_input(strategy: str = "headway_regulation") -> dict[str, Any]:
    """Set a 1000-second run and a 90-second operating gap.

    Include the last departure at 850 seconds.
    Headway holds use the operating cap, not the search cap.
    """
    values = scenario_input(strategy, scenario_gap=90)
    values["duration_s"] = 1000
    return values


def records_from(result: RunResult) -> list[dict[str, Any]]:
    """Read every event from the runner's log."""
    return [json.loads(line) for line in result.events_path.read_text().splitlines()]


def departures(records: Sequence[Mapping[str, Any]]) -> list[tuple[Any, ...]]:
    """Collect departure times, applied holds and delay causes.

    Generated delay includes lateness from holds; disruption delay excludes it.
    Keep every departure to catch missing or duplicate events.
    """
    return event_tuples(
        records,
        "train_departure",
        (
            *MOVEMENT,
            "hold_s",
            "generated_delay_s",
            "disruption_delay_s",
            "inherited_delay_s",
        ),
    )


def holds(records: Sequence[Mapping[str, Any]]) -> list[tuple[Any, ...]]:
    """Collect every requested and applied hold, including refused requests."""
    return event_tuples(
        records, "hold", (*MOVEMENT, "requested_s", "applied_s", "reason")
    )


def assert_baseline_events(
    records: Sequence[Mapping[str, Any]],
    strategy: str,
    departure: float,
    applied: float,
    gaps: list[float],
) -> None:
    """Check exact baseline events before comparing output files.

    B is ready at 250 + 30 = 280; its gap is 280 - 100 = 180.
    Holding 120 seconds reaches its timetable and the 300-second target.
    B's earliness absorbs the hold, so it adds no lateness.
    Exact lists catch extra, missing and zero-length holds.
    """
    assert event_tuples(records, "train_arrival", MOVEMENT) == [
        ("A", "P", 70),
        ("B", "P", 250),
        ("C", "P", 670),
    ]
    assert event_tuples(records, "departure_due", MOVEMENT) == [
        ("A", "P", 100),
        ("B", "P", 280),
        ("C", "P", 700),
    ]
    assert departures(records) == [
        ("A", "P", 100, 0, 0, 0, 0),
        ("B", "P", departure, applied, 0, 0, 0),
        ("C", "P", 700, 0, 0, 0, 0),
    ]
    expected_holds = [("B", "P", 280, 120, 120, strategy)] if applied else []
    assert holds(records) == expected_holds
    expected_ends = [("B", "P", 400)] if applied else []
    assert event_tuples(records, "hold_end", MOVEMENT) == expected_ends
    assert event_tuples(records, "departure_clearance", MOVEMENT) == []
    times = [row[2] for row in departures(records)]
    actual_gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
    assert actual_gaps == gaps


@pytest.mark.parametrize(
    ("strategy", "departure", "applied", "gaps"),
    [
        ("no_control", 280, 0, [180, 420]),
        ("schedule_based", 400, 120, [300, 300]),
        ("headway_regulation", 400, 120, [300, 300]),
    ],
)
def test_three_baselines_match_calculated_comparison_and_repeat(
    tmp_path, strategy, departure, applied, gaps
):
    """Repeat each baseline with fresh trains and the same inputs.

    Reusing B would lose its earliness and hold after the first controlled run.
    Check expected events before comparing file bytes.
    Remove only the recording timestamp from each manifest.
    Check saved settings against the inputs too.
    Two equally wrong manifests must not pass just because they match.
    """
    values = comparison_input(strategy)
    results = []
    for name in ("first", "second"):
        trains = [
            train("A", 70, 100),
            train("B", 370, 400, delay=-120),
            train("C", 670, 700),
        ]
        result = run_selected(tmp_path / name, values, trains=trains)
        records = records_from(result)
        assert_baseline_events(records, strategy, departure, applied, gaps)
        results.append(result)
    first, second = results
    assert first.events_path.read_bytes() == second.events_path.read_bytes()
    assert first.summary_path.read_bytes() == second.summary_path.read_bytes()
    manifests = [json.loads(result.manifest_path.read_text()) for result in results]
    for manifest in manifests:
        assert manifest["control"] == values["control"]
        manifest.pop("timestamp")
    assert manifests[0] == manifests[1]


def test_selected_headway_histories_are_platform_local(tmp_path):
    """Keep each platform's departure history separate.

    Q's first departure has no history; its next gap is exactly 200 seconds.
    On P, B is ready at 280 and needs 120 seconds after A leaves at 100.
    Using Q's departure at 250 for B, or P's at 400 for Q2, changes the holds.
    Q sorts after P, so always reading the first platform also fails.
    """
    values = comparison_input()
    values["control"]["target_headways_s"]["Q"] = 200
    trains = [
        train("A", 70, 100),
        train("B", 250, 280),
        train("Q1", 220, 250, platform="Q"),
        train("Q2", 420, 450, platform="Q"),
    ]
    records = records_from(
        run_selected(tmp_path, values, trains=trains, catalog={"P", "Q"})
    )
    assert event_tuples(records, "train_arrival", MOVEMENT) == [
        ("A", "P", 70),
        ("Q1", "Q", 220),
        ("B", "P", 250),
        ("Q2", "Q", 420),
    ]
    assert event_tuples(records, "departure_due", MOVEMENT) == [
        ("A", "P", 100),
        ("Q1", "Q", 250),
        ("B", "P", 280),
        ("Q2", "Q", 450),
    ]
    assert departures(records) == [
        ("A", "P", 100, 0, 0, 0, 0),
        ("Q1", "Q", 250, 0, 0, 0, 0),
        ("B", "P", 400, 120, 120, 0, 0),
        ("Q2", "Q", 450, 0, 0, 0, 0),
    ]
    assert holds(records) == [("B", "P", 280, 120, 120, "headway_regulation")]
    assert event_tuples(records, "hold_end", MOVEMENT) == [("B", "P", 400)]
    assert event_tuples(records, "departure_clearance", MOVEMENT) == []


@pytest.mark.parametrize(
    ("mode", "applied", "departure", "reason", "ends"),
    [
        (
            "CLAMP",
            60,
            460,
            "headway_regulation (clamped to max_hold_time 60 s)",
            [("B", "P", 460)],
        ),
        ("REFUSE", 0, 400, "refused: over max hold 60 s (headway_regulation)", []),
    ],
)
def test_selected_headway_uses_operating_cap(
    tmp_path, mode, applied, departure, reason, ends
):
    """Request 300 - (400 - 200) = 100 seconds, then apply the operating rule.

    The operating cap is 60 seconds; the separate search cap is 90.
    Refusal logs the request without scheduling HoldEnd.
    Both outcomes leave a gap below 300 seconds.
    A capped hold cannot guarantee the target spacing.
    """
    values = comparison_input()
    values["operating_rules"].update(
        max_hold_time=60, rule_action_map={"max_hold_exceeded": mode}
    )
    trains = [train("A", 170, 200), train("B", 370, 400)]
    records = records_from(run_selected(tmp_path, values, trains=trains))
    assert event_tuples(records, "train_arrival", MOVEMENT) == [
        ("A", "P", 170),
        ("B", "P", 370),
    ]
    assert event_tuples(records, "departure_due", MOVEMENT) == [
        ("A", "P", 200),
        ("B", "P", 400),
    ]
    assert departures(records) == [
        ("A", "P", 200, 0, 0, 0, 0),
        ("B", "P", departure, applied, applied, 0, 0),
    ]
    assert holds(records) == [("B", "P", 400, 100, applied, reason)]
    assert event_tuples(records, "hold_end", MOVEMENT) == ends
    assert event_tuples(records, "departure_clearance", MOVEMENT) == []


def test_selected_headway_uses_departure_after_clearance_as_history(tmp_path):
    """Use B's actual departure at 550, not its hold end at 500.

    Dispatch stays blocked until 550, covering B's whole 100-second hold.
    B records hold_s=100 and disruption_delay_s=150.
    C is ready at 650: gap=100, hold=200, disruption=0.
    Using B's hold end would give hold=150; its timetable would give 50.
    """
    values = comparison_input()
    trains = [train("A", 170, 200), train("B", 370, 400), train("C", 620, 650)]
    result = run_selected(
        tmp_path, values, trains=trains, suspensions=[LineSuspension("green", 390, 550)]
    )
    records = records_from(result)
    assert event_tuples(records, "train_arrival", MOVEMENT) == [
        ("A", "P", 170),
        ("B", "P", 370),
        ("C", "P", 620),
    ]
    assert event_tuples(records, "departure_due", MOVEMENT) == [
        ("A", "P", 200),
        ("B", "P", 400),
        ("C", "P", 650),
    ]
    assert holds(records) == [
        ("B", "P", 400, 100, 100, "headway_regulation"),
        ("C", "P", 650, 200, 200, "headway_regulation"),
    ]
    assert event_tuples(records, "hold_end", MOVEMENT) == [
        ("B", "P", 500),
        ("C", "P", 850),
    ]
    assert event_tuples(records, "departure_clearance", MOVEMENT) == [("B", "P", 550)]
    assert departures(records) == [
        ("A", "P", 200, 0, 0, 0, 0),
        ("B", "P", 550, 100, 150, 150, 0),
        ("C", "P", 850, 200, 200, 0, 0),
    ]
    assert [record["event_type"] for record in records if record["time_s"] == 550] == [
        "departure_clearance",
        "train_departure",
    ]
