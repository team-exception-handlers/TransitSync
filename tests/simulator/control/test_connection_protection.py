# AI contribution: 50% or more AI-generated
"""Check the holds and decision logs from connection protection (#51).

Use simple walking probabilities to check passenger counts and costs by hand.
Give each platform different settings to catch using the wrong platform's values.
Times are seconds; benefits and costs are passenger-seconds.
"""

from dataclasses import dataclass, replace

import pytest

from simulator.control.break_even import BreakEvenWeights
from simulator.control.hold_search import HoldSearch, HoldSearchSettings
from simulator.control.interface import (
    CurrentVisitState,
    HoldAction,
    IncomingTransfer,
    ObservationSnapshot,
    PlatformState,
    TrainState,
)
from simulator.control.strategies.connection_protection import (
    ConnectionProtectionStrategy,
)


@dataclass(frozen=True)
class TableCdf:
    """Give the share of passengers who finish walking by each test time."""

    end_fraction: float = 0.875

    def cdf(self, t_s):
        """Look up the share who have arrived within ``t_s`` seconds."""
        return {120.0: 0.75, 135.0: 0.78125, 150.0: self.end_fraction}[t_s]


def configuration():
    """Give each platform different walking, cost and hold settings.

    For a 30 s hold, green catches 60 * (0.875 - 0.75) = 7.5 passengers.
    Its benefit is 7.5 * 300 = 2250 passenger-seconds.
    REM catches 60 * (0.81640625 - 0.75) = 3.984375 passengers.
    Its benefit is 3.984375 * 128 * 2 = 1020 passenger-seconds.
    With 10 passengers on board, either hold costs 10 * 30 = 300.
    REM's 15 s hold saves 330 after costs; its 30 s hold saves 720.
    """
    searches = {
        "green": HoldSearch(
            TableCdf(), BreakEvenWeights(1, 1), HoldSearchSettings(30, 30)
        ),
        "rem": HoldSearch(
            TableCdf(0.81640625), BreakEvenWeights(2, 1), HoldSearchSettings(15, 30)
        ),
    }
    return searches, {"green": 300, "rem": 128}


def snapshot(platform="green", load=10, transfers=True):
    """Set up a train making its hold decision after its scheduled departure.

    The feeder arrives at 100 s and the decision is at 220 s.
    Put another train and group first to catch code that reads the wrong entry.
    """
    groups = (
        IncomingTransfer("other", "elsewhere", 100, 120, 400, 100, 100),
        IncomingTransfer("g1", platform, 40, 120, 400, 100, 60),
    )
    return ObservationSnapshot(
        time_s=220,
        train_id="deciding",
        station_id="mcgill",
        platform_id=platform,
        scheduled_departure_s=190,
        trains=(
            TrainState("other", "other", None, None, None, 0, 900, 1000),
            TrainState("deciding", platform, None, None, None, 0, load, 1000),
        ),
        platforms=(PlatformState(platform, 0, None),),
        current_visit=CurrentVisitState(platform, True),
        incoming_transfers=groups if transfers else (),
    )


@pytest.mark.parametrize(
    ("platform", "load", "expected", "caught", "headway", "durations"),
    [
        (
            "green",
            10,
            (
                HoldAction(
                    "deciding",
                    30,
                    "hold 30 s: 7.5 caught, benefit 2250.0 > cost 300.0 passenger-s",
                ),
            ),
            7.5,
            300,
            [0, 30],
        ),
        (
            "rem",
            10,
            (
                HoldAction(
                    "deciding",
                    30,
                    "hold 30 s: 4.0 caught, benefit 1020.0 > cost 300.0 passenger-s",
                ),
            ),
            3.984375,
            128,
            [0, 15, 30],
        ),
        ("green", 1000, (), 7.5, 300, [0, 30]),
        ("rem", 1000, (), 3.984375, 128, [0, 15, 30]),
    ],
)
def test_platform_inputs_drive_actions_and_audit(
    platform, load, expected, caught, headway, durations
):
    """Check hold requests and logs using each platform's settings.

    With 1000 passengers on board, holding costs more than it saves.
    REM's reason rounds 3.984375 passengers to 4.0; the log keeps the full value.
    """
    strategy = ConnectionProtectionStrategy(*configuration())
    assert strategy.evaluate(snapshot(platform, load)) == expected
    [record] = strategy.decision_records()
    assert record["train_id"] == "deciding"
    assert record["platform_id"] == platform
    assert record["inputs"] == {
        "load": load,
        "headway_s": headway,
        "transfers": [{"group_id": "g1", "group_size": 60, "conn_window_s": 120}],
    }
    assert [c["hold_s"] for c in record["candidates"]] == durations
    assert record["candidates"][-1]["n_caught"] == caught
    assert record["chosen_hold_s"] == (30 if expected else 0)
    assert record["reason"].startswith("hold" if expected else "no hold")
    if expected:
        assert record["reason"] == expected[0].reason


def test_unprotected_departure_has_no_action_or_audit():
    """Skip other platforms without needing their walking model or train data."""
    strategy = ConnectionProtectionStrategy(*configuration())
    observation = replace(
        snapshot("elsewhere"), trains=(), current_visit=None, platforms=()
    )
    assert strategy.evaluate(observation) == ()
    assert strategy.decision_records() == ()


def test_protected_departure_with_no_groups_is_audited():
    """Log the decision even when nobody is walking to a configured platform."""
    strategy = ConnectionProtectionStrategy(*configuration())
    assert strategy.evaluate(snapshot(transfers=False)) == ()
    [record] = strategy.decision_records()
    assert record["inputs"]["transfers"] == []
    assert record["chosen_hold_s"] == 0
    assert record["reason"] == "no hold: no transfer group is walking to this platform"


def test_caller_mapping_changes_do_not_change_decisions():
    """Changes to the original settings must not change the strategy's decision."""
    searches, headways = configuration()
    strategy = ConnectionProtectionStrategy(searches, headways)
    searches.clear()
    headways["green"] = 1
    assert strategy.evaluate(snapshot()) == (
        HoldAction(
            "deciding",
            30,
            "hold 30 s: 7.5 caught, benefit 2250.0 > cost 300.0 passenger-s",
        ),
    )


def test_audit_is_isolated_between_strategy_instances():
    """Making a decision in one strategy must not add records to another's log."""
    first = ConnectionProtectionStrategy(*configuration())
    second = ConnectionProtectionStrategy(*configuration())
    first.evaluate(snapshot())
    assert len(first.decision_records()) == 1
    assert second.decision_records() == ()


def test_equal_configuration_does_not_make_runs_equal():
    """Controllers belong to separate runs even before their histories diverge."""
    first = ConnectionProtectionStrategy(*configuration())
    second = ConnectionProtectionStrategy(*configuration())
    assert first != second
    first.evaluate(snapshot())
    assert first != second


def test_strategy_dictionary_keys_survive_audit_updates():
    """Identity hashing keeps per-run entries distinct as decision logs grow."""
    first = ConnectionProtectionStrategy(*configuration())
    second = ConnectionProtectionStrategy(*configuration())
    runs = {first: "first run", second: "second run"}
    first.evaluate(snapshot())
    assert runs[first] == "first run"
    assert runs[second] == "second run"


@pytest.mark.parametrize(
    ("searches", "headways", "message"),
    [
        (None, {}, "searches must be a mapping"),
        ({}, None, "headways_s must be a mapping"),
        ({"green": HoldSearch(TableCdf())}, {}, "headways_s.*same platforms"),
        ({}, {"green": 300}, "headways_s.*same platforms"),
        ({" ": HoldSearch(TableCdf())}, {" ": 300}, "platform ID"),
        ({"green": None}, {"green": 300}, "searches.*green.*HoldSearch"),
        ({"green": HoldSearch(TableCdf())}, {"green": 0}, "headways_s.*green"),
        ({"green": HoldSearch(TableCdf())}, {"green": 10**1000}, "headways_s.*green"),
    ],
)
def test_invalid_configuration_fails_at_construction(searches, headways, message):
    """Reject missing or invalid settings when the strategy is created.

    Both maps must list the same platforms and contain valid values.
    The shared number-checking helper has its own tests for other bad numbers.
    """
    with pytest.raises(ValueError, match=message):
        ConnectionProtectionStrategy(searches, headways)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        # The message names the deciding train, platform and time from snapshot()
        ({"current_visit": None}, "current_visit .* for deciding at green, t=220 s"),
        ({"platforms": ()}, "platform history for deciding at green, t=220 s"),
    ],
)
def test_protected_departure_requires_clearance(changes, message):
    strategy = ConnectionProtectionStrategy(*configuration())
    observation = replace(snapshot(), **changes)
    with pytest.raises(ValueError, match=message):
        strategy.evaluate(observation)
    assert strategy.decision_records() == ()


@pytest.mark.parametrize(
    ("platform", "caught", "benefit"),
    [
        ("green", 5.625, 1687.5),
        ("rem", 2.109375, 540),
    ],
)
def test_both_directions_exclude_their_mandatory_wait(platform, caught, benefit):
    """Each destination keeps its own walking model, headway and clearance."""
    strategy = ConnectionProtectionStrategy(*configuration())
    context = replace(snapshot(platform), platforms=(PlatformState(platform, 0, 145),))
    [action] = strategy.evaluate(context)
    [record] = strategy.decision_records()
    # Ready 220, gap floor 145+90=235; request 30 departs 250, adding 15 s.
    # M=60: green 60*(.875-.78125)=5.625; REM 60*(.81640625-.78125)=2.109375.
    assert action.duration_s == 30
    assert record["no_hold_departure_s"] == 235
    chosen = record["candidates"][-1]
    assert chosen["n_caught"] == caught
    assert chosen["benefit_ps"] == benefit
    assert chosen["cost_ps"] == 150
    assert chosen["departure_s"] == 250
    assert chosen["incremental_delay_s"] == 15
