# AI contribution: 50% or more AI-generated
"""Check connection protection settings built from transfer routes (#51).

Passenger generation and control must use the same walking mean and minimum.
Check the chosen hold against a separate calculation using the walking model.
Errors about platforms or walk times must identify the affected routes.

The saved-setting cases change one input at a time.
A larger waiting weight can make a longer hold worthwhile.
A smaller service headway can make every hold unprofitable.
Different walk times can move the best hold away from the upper limit.
The search grid controls which hold lengths can be chosen.
Each result includes one audit record with the supplied settings.
The full-run tests check how these proposals affect actual departures.
"""

import json
from dataclasses import replace
from datetime import date

import pytest

from simulator.control.break_even import BreakEvenWeights
from simulator.control.connection_configuration import (
    build_connection_protection,
    build_selected_connection_protection,
)
from simulator.control.hold_search import HoldSearchSettings
from simulator.control.interface import (
    HoldAction,
    IncomingTransfer,
    ObservationSnapshot,
    TrainState,
)
from simulator.control.settings import ControlSettings
from simulator.passengers import (
    CorridorQueue,
    DemandPeriod,
    DemandProfile,
    TransferRoute,
)
from simulator.scenario import DatasetMetadata, load_scenario_json

PLATFORMS = ("rem", "green", "orange")


def load_selected(headway, wait_weight, step, bound, *, onboard_weight=1):
    """Load saved connection settings using local dataset metadata.

    Custom weights and search limits must reach the actual strategy.
    The route's walking values are supplied separately to passenger generation.
    """
    dataset = DatasetMetadata(
        "test",
        date(2026, 10, 5),
        date(2026, 10, 5),
        {"mcgill": 86400},
        frozenset({"mcgill"}),
    )
    values = {
        "dataset_id": "test",
        "date": "2026-10-05",
        "start_time": "07:00",
        "interchanges": ["mcgill"],
        "control": {
            "strategy": "connection_protection",
            "connection_headways_s": {"green": headway},
            "weights": {"w_wait": wait_weight, "w_onboard": onboard_weight},
            "hold_search": {"step_s": step, "max_hold_s": bound},
        },
    }
    return load_scenario_json(json.dumps(values), {"test": dataset})


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


def test_direct_builder_keeps_decision_history():
    """Keep a hold followed by a no-hold decision in order.

    N(h) = 80 * exp(-30/120) * (1 - exp(-h/120)). With H=300 and L=100,
    J(40), J(50), J(60) are 1298.375, 1369.208, 1354.422 passenger-seconds.
    J has one peak, so 50 s wins among 10 s steps. It catches 21.23069312.
    Adding the second decision must leave the first record unchanged.
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
    assert (
        strategy.evaluate(replace(observation, time_s=170, incoming_transfers=())) == ()
    )
    first, second = strategy.decision_records()
    assert first == record
    assert (second["time_s"], second["chosen_hold_s"]) == (170, 0)


@pytest.mark.parametrize(
    "values, reason",
    [
        # The reference case wins below the 90 s bound.
        (
            (300, 1, 1, 120, 10, 90, 60, 6000),
            "hold 60 s: 27.9 caught, benefit 8367.6 > cost 6000.0 passenger-s",
        ),
        # A larger waiting weight makes the 90 s hold win.
        (
            (300, 2, 1, 120, 10, 90, 90, 9000),
            "hold 90 s: 36.2 caught, benefit 21740.8 > cost 9000.0 passenger-s",
        ),
        # With H=150 s, even the best hold costs more than it saves.
        (
            (150, 1, 1, 120, 10, 90, 0, 0),
            "no hold: best was 10 s: 6.0 caught, "
            "benefit 904.2 <= cost 1000.0 passenger-s",
        ),
        # A longer mean walk moves the best hold to 50 s.
        (
            (300, 1, 1, 150, 10, 90, 50, 5000),
            "hold 50 s: 21.2 caught, benefit 6369.2 > cost 5000.0 passenger-s",
        ),
        # The shorter grid ends at 45 s, which becomes the winner.
        (
            (300, 1, 1, 120, 15, 45, 45, 4500),
            "hold 45 s: 22.6 caught, benefit 6766.4 > cost 4500.0 passenger-s",
        ),
        # With onboard weight 1.5, J(10), J(20), J(30) are 308.422, 426.669,
        # and 374.741 passenger-seconds. The 20 s hold costs 100*20*1.5=3000.
        (
            (300, 1, 1.5, 120, 10, 90, 20, 3000),
            "hold 20 s: 11.4 caught, benefit 3426.7 > cost 3000.0 passenger-s",
        ),
    ],
)
def test_saved_configuration_drives_selected_hold(values, reason):
    """Saved settings must change the chosen hold, not just parse successfully.

    With M=80, s=60 s and L=100, calculate independently:
    N(h)=80*exp(-30/(mean-30))*(1-exp(-h/(mean-30))).
    J(h)=N(h)*headway*wait_weight-100*h*onboard_weight.
    The table gives the best grid values and their hand-calculated costs.
    Change one input at a time to catch lost headways, weights, routes or limits.
    """
    headway, wait_weight, onboard_weight, mean, step, bound, chosen, cost = values
    scenario = load_selected(
        headway, wait_weight, step, bound, onboard_weight=onboard_weight
    )
    routes = [transfer_route(walking_mean_s=mean)]
    strategy = build_selected_connection_protection(scenario.control, routes, PLATFORMS)
    expected = (HoldAction("green-1", chosen, reason),) if chosen else ()
    assert strategy.evaluate(decision_snapshot()) == expected
    [record] = strategy.decision_records()
    assert record["chosen_hold_s"] == chosen
    assert record["reason"] == reason
    assert record["candidates"][chosen // step]["cost_ps"] == cost
    assert record["inputs"] == {
        "load": 100,
        "headway_s": headway,
        "transfers": [{"group_id": "group", "group_size": 80, "conn_window_s": 60}],
    }
    assert record["walking"] == {
        "family": "ShiftedExponentialCdf",
        "mean_s": mean,
        "min_s": 30,
    }
    assert record["weights"] == {
        "w_wait": wait_weight,
        "w_onboard": onboard_weight,
    }
    assert record["hold_search"] == {"step_s": step, "max_hold_s": bound}
    assert [c["hold_s"] for c in record["candidates"]] == list(
        range(0, bound + 1, step)
    )


def test_selected_builder_rejects_another_strategy():
    """Do not force connection protection when the saved selection is different."""
    control = ControlSettings()
    routes = [transfer_route()]
    with pytest.raises(ValueError, match="control.strategy.*connection_protection"):
        build_selected_connection_protection(control, routes, PLATFORMS)


def test_selected_builder_rejects_incomplete_headways():
    """Saved settings still need headways for the actual transfer destinations."""
    scenario = load_selected(300, 1, 10, 90)
    routes = [transfer_route(connecting_platform_id="orange")]
    with pytest.raises(ValueError, match="headways_s.*missing.*orange.*extra.*green"):
        build_selected_connection_protection(scenario.control, routes, PLATFORMS)


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
