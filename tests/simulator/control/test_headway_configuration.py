# AI contribution: 50% or more AI-generated
"""Check target coverage before headway runs start (US-2.3, #48).

Turnaround stops skip departure; ordinary final stops do not.
Returns start after the cutoff, so checking only initial platforms misses them.
Each case changes one platform or gap.
"""

from collections.abc import Collection, Sequence

import pytest

from simulator.control.headway_configuration import validate_headway_configuration
from simulator.control.settings import parse_control_settings
from simulator.trains.train import ScheduledStop, Train

CATALOG = frozenset({"P1", "T-in", "R", "P2", "R2", "P3"})
REQUIRED = ("P1", "R", "R2", "P3")


def returning_train() -> Train:
    """Build three trips; both returns start after the 600-second cutoff.

    Each return starts at the previous trip's last station, on another platform.
    Each turnaround allows at least 60 seconds of recovery.
    """
    return Train(
        "A",
        800,
        (ScheduledStop("S1", "P1", 70, 100), ScheduledStop("TERM", "T-in", 200, 230)),
        layover_slack=60,
        return_trips=(
            (ScheduledStop("TERM", "R", 800, 830), ScheduledStop("S2", "P2", 930, 960)),
            (
                ScheduledStop("S2", "R2", 1200, 1230),
                ScheduledStop("S3", "P3", 1330, 1360),
            ),
        ),
    )


def validate(
    targets: object,
    trains: Sequence[Train],
    catalog: Collection[str] = CATALOG,
    gap: float = 90,
) -> None:
    """Check trips, platforms and gap using parsed settings.

    Allow bad target inputs here so the real parser checks them first.
    """
    control = parse_control_settings(
        {"strategy": "headway_regulation", "target_headways_s": targets}
    )
    return validate_headway_configuration(control, trains, catalog, gap)


@pytest.mark.parametrize("missing", ["P1", "R", "R2", "P3"])
def test_every_ordinary_platform_requires_a_target(missing):
    """Reject missing targets on initial, return and final departure platforms."""
    targets = dict.fromkeys(
        (platform for platform in REQUIRED if platform != missing), 300
    )
    trains = [returning_train()]
    with pytest.raises(ValueError, match=f"Missing target.*{missing}"):
        validate(targets, trains)


def test_turnaround_platforms_do_not_require_targets():
    """T-in and P2 skip departure and need no targets."""
    targets = dict.fromkeys(REQUIRED, 300)
    assert validate(targets, [returning_train()]) is None


def test_terminal_without_return_requires_a_target():
    """A final stop needs a target when no return follows."""
    original = returning_train()
    train = Train("A", 800, original.schedule)
    targets = {"P1": 300}
    trains = [train]
    with pytest.raises(ValueError, match="Missing target.*T-in"):
        validate(targets, trains)


def test_terminal_without_return_accepts_complete_targets():
    """A final stop is valid when its target is supplied."""
    train = Train("A", 800, returning_train().schedule)
    assert validate({"P1": 300, "T-in": 300}, [train]) is None


def test_turnaround_platform_used_by_another_train_still_requires_target():
    """Skipping one visit must not exempt other departures at that platform."""
    other = Train("B", 800, (ScheduledStop("TERM", "T-in", 400, 430),))
    trains = [returning_train(), other]
    targets = dict.fromkeys(REQUIRED, 300)
    with pytest.raises(ValueError, match="Missing target.*T-in"):
        validate(targets, trains)


def test_unknown_target_is_not_ignored_when_coverage_is_complete():
    """Reject an unknown target even when all required targets are present."""
    targets = {**dict.fromkeys(REQUIRED, 300), "TYPO": 300}
    trains = [returning_train()]
    with pytest.raises(ValueError, match="Unknown platform.*TYPO"):
        validate(targets, trains)


def test_matching_target_and_schedule_typos_do_not_define_the_catalog():
    """Matching typos in targets and stops are still unknown platform IDs."""
    trains = [Train("A", 800, (ScheduledStop("S1", "TYPO", 70, 100),))]
    targets = {"TYPO": 300}
    with pytest.raises(ValueError, match="Unknown platform.*TYPO"):
        validate(targets, trains)


def test_unknown_scheduled_platform_is_checked_even_without_target():
    """Even skipped turnaround stops must use known platform IDs."""
    targets = dict.fromkeys(REQUIRED, 300)
    trains = [returning_train()]
    catalog = CATALOG - {"T-in"}
    with pytest.raises(ValueError, match="Unknown platform.*T-in"):
        validate(targets, trains, catalog)


def test_synthetic_catalog_does_not_require_real_network_platforms():
    """A small test can supply its own platform IDs."""
    trains = [Train("synthetic", 800, (ScheduledStop("local", "local-P", 70, 100),))]
    assert validate({"local-P": 300}, trains, {"local-P"}) is None


@pytest.mark.parametrize("target", [89.5, 90, 90.5])
def test_target_boundary_uses_effective_engine_gap(target):
    """Targets may equal or exceed the engine gap, but cannot be shorter."""
    # Put R2 later to catch validation that checks only the first target.
    targets = dict.fromkeys(REQUIRED, 300)
    targets["R2"] = target
    trains = [returning_train()]
    if target < 90:
        with pytest.raises(ValueError, match="R2.*minimum_gap_s"):
            validate(targets, trains)
    else:
        assert validate(targets, trains) is None


def test_effective_gap_is_not_hard_coded_to_default():
    """Use the supplied engine gap, not its 90-second default."""
    assert validate(dict.fromkeys(REQUIRED, 60), [returning_train()], gap=45) is None


@pytest.mark.parametrize(
    "gap", [True, None, "90", 0, -1, float("nan"), float("inf"), 10**400]
)
def test_effective_gap_must_be_valid_engine_seconds(gap):
    """The engine gap must be positive, finite seconds."""
    targets = dict.fromkeys(REQUIRED, 300)
    trains = [returning_train()]
    with pytest.raises(ValueError, match="minimum_gap_s"):
        validate(targets, trains, gap=gap)


@pytest.mark.parametrize("catalog", [None, "P1"])
def test_catalog_must_be_explicit_collection(catalog):
    """Known platform IDs must be a collection, not null or a string."""
    targets = dict.fromkeys(REQUIRED, 300)
    trains = [returning_train()]
    with pytest.raises(ValueError, match="known_platform_ids"):
        validate(targets, trains, catalog)


def test_non_headway_settings_need_no_headway_validation():
    """Other strategies need no headway validation."""
    control = parse_control_settings(None)
    assert validate_headway_configuration(control, [], frozenset(), 90) is None
