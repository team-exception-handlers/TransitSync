# AI contribution: 50% or more AI-generated
"""Check connection protection settings built from transfer routes (#51).

Passenger generation and control must use the same walking mean and minimum.
Check the chosen hold against a separate calculation using the walking model.
Errors about platforms or walk times must identify the affected routes.
"""

from dataclasses import replace

import pytest

from simulator.control.break_even import BreakEvenWeights
from simulator.control.connection_configuration import build_connection_protection
from simulator.control.hold_search import HoldSearchSettings
from simulator.control.interface import (
    HoldAction,
    IncomingTransfer,
    ObservationSnapshot,
    TrainState,
)
from simulator.passengers import (
    CorridorQueue,
    DemandPeriod,
    DemandProfile,
    TransferRoute,
)

PLATFORMS = ("rem", "green", "orange")


def transfer_route(**changes):
    """Make a route with a 150 s mean and 30 s minimum walk.

    The controller reads these walk times from the passenger route.
    Tests change one value at a time to check platform and walk-time errors.
    """
    route = TransferRoute(
        "mcgill",
        "rem",
        "green",
        DemandProfile((DemandPeriod(0, 1000, 80),)),
        {"bonaventure": 1},
        CorridorQueue(6000),
        walking_mean_s=150,
        walking_min_s=30,
    )
    return replace(route, **changes)


def decision_snapshot():
    """Set up 80 transferring passengers and a train with 100 passengers aboard.

    The decision is 60 s after the feeder arrives. The earlier scheduled
    departure must not be used to calculate that time window.
    """
    return ObservationSnapshot(
        time_s=160,
        train_id="green-1",
        station_id="mcgill",
        platform_id="green",
        scheduled_departure_s=130,
        trains=(TrainState("green-1", "green", None, None, None, 0, 100, 800),),
        platforms=(),
        incoming_transfers=(IncomingTransfer("group", "green", 80, 130, 400, 100, 80),),
    )


def test_route_inputs_choose_an_interior_hold_and_keep_decision_history():
    """Choose a 50 s hold when the search allows up to 90 s.

    N(h) = 80 * exp(-30/120) * (1 - exp(-h/120)). With H=300 and L=100,
    J(40), J(50), J(60) are 1298.375, 1369.208, 1354.422 passenger-seconds.
    J has one peak, so 50 s wins among 10 s steps. It catches 21.23069312.
    A later no-hold decision must be logged after the first decision.
    """
    strategy = build_connection_protection(
        [transfer_route()],
        {"green": 300},
        PLATFORMS,
        weights=BreakEvenWeights(1, 1),
        settings=HoldSearchSettings(10, 90),
    )
    observation = decision_snapshot()
    reason = "hold 50 s: 21.2 caught, benefit 6369.2 > cost 5000.0 passenger-s"
    assert strategy.evaluate(observation) == (HoldAction("green-1", 50, reason),)
    [record] = strategy.decision_records()
    assert record["inputs"] == {
        "load": 100,
        "headway_s": 300,
        "transfers": [{"group_id": "group", "group_size": 80, "conn_window_s": 60}],
    }
    assert record["walking"] == {
        "family": "ShiftedExponentialCdf",
        "mean_s": 150,
        "min_s": 30,
    }
    assert record["weights"] == {"w_wait": 1, "w_onboard": 1}
    assert record["hold_search"] == {"step_s": 10, "max_hold_s": 90}
    assert [c["hold_s"] for c in record["candidates"]] == list(range(0, 91, 10))
    assert record["chosen_hold_s"] == 50
    assert record["reason"] == reason
    # Allow rounding because the hand-calculated count has eight decimal places.
    assert record["candidates"][5]["n_caught"] == pytest.approx(21.23069312, abs=1e-8)
    assert (
        strategy.evaluate(replace(observation, time_s=170, incoming_transfers=())) == ()
    )
    first, second = strategy.decision_records()
    assert first == record
    assert (second["time_s"], second["chosen_hold_s"]) == (170, 0)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"feeder_platform_id": "missing"}, "feeder_platform_id.*missing.*mcgill"),
        (
            {"connecting_platform_id": "missing"},
            "connecting_platform_id.*missing.*mcgill",
        ),
    ],
)
def test_unknown_route_platform_fails_preflight(changes, message):
    """Reject unknown route platforms before the simulation starts.

    The error must name the field, unknown platform and route's station.
    """
    routes = [transfer_route(**changes)]
    with pytest.raises(ValueError, match=message):
        build_connection_protection(routes, {"green": 300}, PLATFORMS)


@pytest.mark.parametrize(
    "headways, message",
    [
        ({}, "headways_s.*missing.*green"),
        ({"green": 300, "rem": 300}, "headways_s.*extra.*rem"),
    ],
)
def test_headways_cover_exactly_transfer_destinations(headways, message):
    """Require headways only for platforms that receive transfers."""
    routes = [transfer_route()]
    with pytest.raises(ValueError, match=message):
        build_connection_protection(routes, headways, PLATFORMS)


@pytest.mark.parametrize("mean_s, min_s", [(151, 30), (150, 31)])
def test_conflicting_profiles_name_destination_routes_and_values(mean_s, min_s):
    """Reject routes to one platform if their walking mean or minimum differs.

    Both values must match so the routes can use one walking model.
    The error must show both routes and the values that need fixing.
    """
    routes = [
        transfer_route(),
        transfer_route(
            feeder_platform_id="orange",
            walking_mean_s=mean_s,
            walking_min_s=min_s,
        ),
    ]
    with pytest.raises(ValueError, match="walking.*green") as error:
        build_connection_protection(routes, {"green": 300}, PLATFORMS)
    message = str(error.value)
    for detail in ("mcgill", "rem", "orange", "150", "30", str(mean_s), str(min_s)):
        assert detail in message


def test_matching_profiles_share_one_search():
    """Accept two routes to one platform when both walking values match.

    The destination platform needs one headway, shared by both routes.
    """
    routes = [transfer_route(), transfer_route(feeder_platform_id="orange")]
    strategy = build_connection_protection(routes, {"green": 300}, PLATFORMS)
    assert tuple(strategy.searches) == ("green",)
    assert strategy.searches["green"].walking.mean_s == 150
    assert strategy.searches["green"].walking.min_s == 30


@pytest.mark.parametrize(
    ("routes", "headways", "platforms", "message"),
    [
        (None, {}, PLATFORMS, "routes"),
        ("rem", {}, PLATFORMS, "routes"),
        ([None], {}, PLATFORMS, "routes"),
        ([], None, PLATFORMS, "headways_s"),
        ([], {}, None, "platform_ids"),
        ([], {}, "rem", "platform_ids"),
        ([], {}, (" ",), "platform_ids"),
        ([], {}, (None,), "platform_ids"),
    ],
)
def test_malformed_construction_inputs_fail_preflight(
    routes, headways, platforms, message
):
    """Give clear errors for invalid route lists, headway maps and platform IDs.

    Existing strategy tests check invalid headway numbers.
    These cases check the types of inputs passed to the new helper.
    """
    with pytest.raises(ValueError, match=message):
        build_connection_protection(routes, headways, platforms)


def test_each_destination_uses_its_own_route_profile():
    """Allow different walk times and headways in each transfer direction.

    Walking values must match only for routes to the same platform.
    Each destination gets the walking model from its own route.
    """
    routes = [
        transfer_route(),
        transfer_route(
            feeder_platform_id="green",
            connecting_platform_id="rem",
            walking_mean_s=240,
            walking_min_s=60,
        ),
    ]
    strategy = build_connection_protection(
        routes, {"green": 300, "rem": 600}, PLATFORMS
    )
    assert tuple(strategy.searches) == ("green", "rem")
    assert strategy.searches["green"].walking.mean_s == 150
    assert strategy.searches["rem"].walking.mean_s == 240
    assert strategy.searches["rem"].walking.min_s == 60
    assert dict(strategy.headways_s) == {"green": 300, "rem": 600}
