# AI contribution: 50% or more AI-generated
"""Interchange extraction with full-trip context."""

from dataclasses import FrozenInstanceError, replace

import pytest

from scripts.gtfs_schedule import extract_trips
from simulator.timetable import Platform, ScheduledVisit


@pytest.fixture
def platform():
    return Platform(
        platform_id="rem-mcgill-1",
        interchange_id="mcgill",
        line_id="rem",
        direction_id=1,
        stop_id="MCG",
        stop_name="McGill quai 2",
        route_ids=("S1",),
        direction_label="Brossard",
    )


def visit(stop_id, sequence, arrival, *, pickup=0, drop_off=0, **extra):
    return dict(
        feed_id="rem",
        trip_id="trip",
        stop_id=stop_id,
        stop_sequence=sequence,
        arrival_s=arrival,
        departure_s=arrival + 30,
        pickup_type=pickup,
        drop_off_type=drop_off,
        **extra,
    )


def extract(platform, visits, *, trips=None, stops=None, services=("weekday",)):
    return extract_trips(
        feed_id="rem",
        service_ids=services,
        platforms=(platform,),
        routes=[dict(feed_id="rem", route_id="S1", route_type=0)],
        stops=stops
        or [
            dict(feed_id="rem", stop_id=s, stop_name=name, location_type=0)
            for s, name in [
                ("UP", "Upstream"),
                ("MCG", "McGill quai 2"),
                ("DOWN", "Downstream"),
            ]
        ],
        trips=trips
        if trips is not None
        else [
            dict(
                feed_id="rem",
                trip_id="trip",
                service_id="weekday",
                route_id="S1",
                direction_id=1,
                trip_headsign="Brossard",
            )
        ],
        stop_times=visits,
    )


def test_full_trip_context_survives_trimming_to_first_modeled_visit(platform):
    # Unmodeled stops still establish boarding and alighting opportunities.
    trips = extract(
        platform, [visit("DOWN", 30, 200), visit("UP", 10, 100), visit("MCG", 20, 150)]
    )
    train = trips[0]
    assert train.trip_id == "trip"
    assert train.destination == "Brossard"
    assert len(train.visits) == 1
    stop = train.visits[0]
    assert (stop.arrival_s, stop.departure_s, stop.stop_sequence) == (150, 180, 20)
    assert stop.incoming_passenger_service and stop.outgoing_passenger_service
    assert stop.boarding_allowed and stop.alighting_allowed
    assert stop.has_earlier_boarding and stop.has_later_alighting
    assert (stop.pickup_type, stop.drop_off_type) == (0, 0)
    with pytest.raises(FrozenInstanceError):
        stop.arrival_s = 0


def test_real_source_origin_has_physical_visit_but_no_incoming_passengers(platform):
    stop = extract(platform, [visit("MCG", 10, 100), visit("DOWN", 20, 200)])[0].visits[
        0
    ]
    assert stop.alighting_allowed
    assert not stop.incoming_passenger_service
    assert stop.outgoing_passenger_service


def test_source_terminus_cannot_offer_onward_service_even_with_regular_pickup(platform):
    stop = extract(platform, [visit("UP", 1, 100), visit("MCG", 2, 200)])[0].visits[0]
    assert stop.boarding_allowed
    assert stop.incoming_passenger_service
    assert not stop.outgoing_passenger_service


def test_permission_checks_use_all_earlier_and_later_stops_not_just_neighbors(platform):
    rows = [
        visit("UP", 1, 100),
        visit("UP", 2, 140, pickup=1),
        visit("MCG", 3, 180),
        visit("DOWN", 4, 220, drop_off=1),
        visit("DOWN", 5, 260),
    ]
    stop = extract(platform, rows)[0].visits[0]
    assert stop.incoming_passenger_service and stop.outgoing_passenger_service
    rows[0]["pickup_type"] = 1
    rows[-1]["drop_off_type"] = 1
    stop = extract(platform, rows)[0].visits[0]
    assert not stop.incoming_passenger_service
    assert not stop.outgoing_passenger_service


def test_local_permissions_override_existing_upstream_and_downstream_service(platform):
    rows = [
        visit("UP", 1, 100),
        visit("MCG", 2, 150, pickup=1, drop_off=1),
        visit("DOWN", 3, 200),
    ]
    stop = extract(platform, rows)[0].visits[0]
    assert stop.has_earlier_boarding and stop.has_later_alighting
    assert not stop.incoming_passenger_service
    assert not stop.outgoing_passenger_service


def test_overnight_seconds_and_repeated_stop_visits_remain_ordered(platform):
    rows = [
        visit("UP", 1, 86000),
        visit("MCG", 2, 86500),
        visit("MCG", 3, 87000),
        visit("DOWN", 4, 88000),
    ]
    train = extract(platform, rows)[0]
    assert [v.arrival_s for v in train.visits] == [86500, 87000]
    assert [v.stop_sequence for v in train.visits] == [2, 3]
    assert train == extract(platform, list(reversed(rows)))[0]


@pytest.mark.parametrize(
    "field,value",
    [
        ("arrival_s", None),
        ("arrival_s", True),
        ("arrival_s", -1),
        ("departure_s", 99),
        ("pickup_type", None),
        ("drop_off_type", 9),
        ("stop_sequence", -1),
        ("stop_sequence", 1.5),
    ],
)
def test_invalid_source_values_name_the_field(platform, field, value):
    rows = [visit("MCG", 1, 100) | {field: value}]
    with pytest.raises(ValueError, match=field):
        extract(platform, rows)


@pytest.mark.parametrize("stop_id", [" MCG", "MCG ", "\tMCG\n"])
def test_padded_source_stop_ids_fail_instead_of_silently_dropping_service(
    platform, stop_id
):
    rows = [visit("UP", 1, 100), visit(stop_id, 2, 150), visit("DOWN", 3, 200)]
    with pytest.raises(
        ValueError, match="feed 'rem', trip 'trip': stop_id.*whitespace"
    ):
        extract(platform, rows)


@pytest.mark.parametrize("route_id", [" S1", "S1 ", "\tS1\n"])
def test_padded_source_route_ids_fail_instead_of_silently_dropping_service(
    platform, route_id
):
    trip = dict(
        feed_id="rem",
        trip_id="trip",
        service_id="weekday",
        route_id=route_id,
        direction_id=1,
        trip_headsign="Brossard",
    )
    rows = [visit("UP", 1, 100), visit("MCG", 2, 150), visit("DOWN", 3, 200)]
    with pytest.raises(ValueError, match="trip 'trip': route_id.*whitespace"):
        extract(platform, rows, trips=[trip])


def test_duplicate_sequence_and_backwards_trip_times_are_rejected(platform):
    with pytest.raises(ValueError, match="duplicate.*stop_sequence"):
        extract(platform, [visit("UP", 1, 100), visit("MCG", 1, 150)])
    with pytest.raises(ValueError, match="chronological"):
        extract(platform, [visit("UP", 1, 200), visit("MCG", 2, 100)])


def test_mapping_mismatch_is_actionable(platform):
    with pytest.raises(ValueError, match="mapping.*stop_name"):
        extract(replace(platform, stop_name="Wrong"), [visit("MCG", 1, 100)])
    with pytest.raises(ValueError, match="mapping.*route"):
        extract(replace(platform, route_ids=("missing",)), [visit("MCG", 1, 100)])


def test_opposite_directions_with_one_source_stop_stay_separate(platform):
    opposite = replace(platform, direction_id=0, platform_id="rem-mcgill-0")
    trains = [
        dict(
            feed_id="rem",
            trip_id=f"t{d}",
            service_id="weekday",
            route_id="S1",
            direction_id=d,
            trip_headsign="Destination",
        )
        for d in (0, 1)
    ]
    rows = [visit("MCG", 1, 100) | {"trip_id": f"t{d}"} for d in (0, 1)]
    result = extract_trips(
        feed_id="rem",
        service_ids=("weekday",),
        platforms=(platform, opposite),
        routes=[dict(feed_id="rem", route_id="S1", route_type=0)],
        stops=[
            dict(
                feed_id="rem", stop_id="MCG", stop_name="McGill quai 2", location_type=0
            )
        ],
        trips=trains,
        stop_times=rows,
    )
    assert [t.visits[0].platform_id for t in result] == ["rem-mcgill-0", "rem-mcgill-1"]


def test_other_feed_and_inactive_trip_rows_do_not_contaminate_selected_schedule(
    platform,
):
    rows = [visit("MCG", 1, 100), visit("MCG", 1, 0) | {"feed_id": "other"}]
    assert len(extract(platform, rows)) == 1
    assert extract(platform, rows, services=("different-service",)) == ()


def test_no_active_services_are_rejected(platform):
    with pytest.raises(ValueError, match="feed 'rem'.*no active services"):
        extract(platform, [], services=iter(()))


def test_distinct_identical_trains_are_preserved(platform):
    trips = [
        dict(
            feed_id="rem",
            trip_id=t,
            service_id="weekday",
            route_id="S1",
            direction_id=1,
            trip_headsign="Brossard",
        )
        for t in ("a", "b")
    ]
    rows = [visit("MCG", 1, 100) | {"trip_id": t} for t in ("a", "b")]
    assert [t.trip_id for t in extract(platform, rows, trips=trips)] == ["a", "b"]


def test_missing_complete_trip_rows_or_unknown_stops_fail(platform):
    with pytest.raises(ValueError, match="stop_times"):
        extract(platform, [])
    with pytest.raises(ValueError, match="stop_id"):
        extract(platform, [visit("unknown", 1, 100)])


def test_visit_contract_rejects_inconsistent_or_missing_facts():
    with pytest.raises(ValueError, match="has_earlier_boarding"):
        ScheduledVisit(
            platform_id="p",
            stop_id="s",
            stop_sequence=1,
            arrival_s=0,
            departure_s=1,
            pickup_type=0,
            drop_off_type=0,
            has_earlier_boarding=1,
            has_later_alighting=False,
        )


def test_mapping_cannot_silently_drop_a_reversed_source_direction(platform):
    wrong_direction = replace(platform, direction_id=0)
    with pytest.raises(ValueError, match="mapping.*direction"):
        extract(wrong_direction, [visit("MCG", 1, 100)])


def test_duplicate_source_trip_or_stop_identifiers_fail(platform):
    duplicate = dict(
        feed_id="rem",
        trip_id="t",
        service_id="weekday",
        route_id="S1",
        direction_id=1,
        trip_headsign="Brossard",
    )
    with pytest.raises(ValueError, match="duplicate trip_id"):
        extract(platform, [], trips=[duplicate, duplicate])
    stop = dict(
        feed_id="rem", stop_id="MCG", stop_name="McGill quai 2", location_type=0
    )
    with pytest.raises(ValueError, match="duplicate stop_id"):
        extract(platform, [], stops=[stop, stop])
