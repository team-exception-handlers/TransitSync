# AI contribution: 50% or more AI-generated
"""Offline config loading and record consistency."""

import copy
import json
from dataclasses import asdict
from datetime import date

import pytest

from simulator.network_config import REM_ATTRIBUTION, load_network, validate_network
from simulator.timetable import (
    Platform,
    ScheduledTrip,
    ScheduledVisit,
    summarize_headways,
)


@pytest.fixture
def config():
    platform = Platform(
        platform_id="p",
        interchange_id="mcgill",
        line_id="rem",
        direction_id=0,
        direction_label="Outbound",
        stop_id="s",
        stop_name="McGill",
        route_ids=("S1",),
    )
    visit = ScheduledVisit(
        platform_id="p",
        stop_id="s",
        stop_sequence=2,
        arrival_s=28800,
        departure_s=28830,
        pickup_type=0,
        drop_off_type=0,
        has_earlier_boarding=True,
        has_later_alighting=True,
    )
    trip = ScheduledTrip(
        feed_id="f",
        trip_id="t",
        service_id="day",
        route_id="S1",
        direction_id=0,
        destination="Destination",
        visits=(visit,),
    )
    dates = {"weekday": "2026-10-05", "saturday": "2026-10-10", "sunday": "2026-10-11"}
    days = [
        dict(
            service_date=d,
            timezone="America/Toronto",
            platforms=[asdict(platform) | {"feed_id": "f"}],
            trips=[trip.to_dict()],
            feeds=[
                dict(
                    feed_id="f",
                    agency="REM",
                    feed_version="v1",
                    downloaded_on="2026-10-12",
                    coverage_start="2026-06-15",
                    coverage_end="2026-10-25",
                    service_ids=["day"],
                )
            ],
            attribution=[REM_ATTRIBUTION],
            headways=summarize_headways((platform,), (trip,)),
        )
        for d in dates.values()
    ]
    result = dict(
        schema_version=1,
        kind="representative_schedules",
        timezone="America/Toronto",
        reference_dates=dates,
        schedules=days,
        map_evidence=[
            dict(
                url="https://www.stm.info/map.pdf",
                checked_on="2026-10-19",
                notes="Interchanges checked",
            )
        ],
        attribution=[REM_ATTRIBUTION],
    )
    return json.loads(json.dumps(result))


def test_offline_reader_exposes_only_saved_dates_and_immutable_trips(tmp_path, config):
    path = tmp_path / "network.json"
    path.write_text(json.dumps(config))
    network = load_network(path)
    assert network.reference_dates["saturday"] == date(2026, 10, 10)
    trip = network.trips_for_date(date(2026, 10, 5))[0]
    assert trip.visits[0].outgoing_passenger_service
    assert all(
        network.platform_feed_ids[platform.platform_id] == "f"
        for platform in network.platforms
    )
    with pytest.raises(ValueError, match="not extracted"):
        network.trips_for_date(date(2026, 10, 6))
    with pytest.raises(TypeError):
        network.reference_dates["weekday"] = date(2026, 10, 6)


@pytest.mark.parametrize("platform_id", [" p", "p ", "\tp\n"])
def test_padded_saved_platform_ids_fail_instead_of_returning_broken_feed_mapping(
    config, platform_id
):
    for day in config["schedules"]:
        day["platforms"][0]["platform_id"] = platform_id
    with pytest.raises(ValueError, match="platform_id.*whitespace"):
        validate_network(config)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("kind", "full_calendar"),
        ("timezone", "UTC"),
        ("schedules", []),
        ("unexpected", 1),
    ],
)
def test_invalid_top_level_contract_is_rejected(config, field, value):
    config[field] = value
    with pytest.raises(ValueError):
        validate_network(config)


@pytest.mark.parametrize(
    "mutation",
    [
        "boarding",
        "platform",
        "feed",
        "route",
        "service",
        "direction",
        "stop",
        "duplicate_trip",
        "summary",
        "date",
        "coverage",
        "topology",
        "feed_version",
    ],
)
def test_inconsistent_saved_records_fail(config, mutation):
    day = config["schedules"][0]
    trip = day["trips"][0]
    visit = trip["visits"][0]
    if mutation == "boarding":
        visit["boarding_allowed"] = False
    elif mutation == "platform":
        visit["platform_id"] = "unknown"
    elif mutation == "feed":
        trip["feed_id"] = "unknown"
    elif mutation == "route":
        trip["route_id"] = "unknown"
    elif mutation == "service":
        trip["service_id"] = "unknown"
    elif mutation == "direction":
        trip["direction_id"] = 1
    elif mutation == "stop":
        visit["stop_id"] = "unknown"
    elif mutation == "duplicate_trip":
        day["trips"].append(copy.deepcopy(trip))
    elif mutation == "summary":
        day["headways"][0]["bands"][1]["departure_count"] = 999
    elif mutation == "date":
        day["service_date"] = "2026-10-06"
    elif mutation == "coverage":
        day["feeds"][0]["coverage_end"] = "2026-01-01"
    elif mutation == "topology":
        day["platforms"][0]["stop_name"] = "Changed"
    elif mutation == "feed_version":
        day["feeds"][0]["feed_version"] = "different"
    with pytest.raises(ValueError):
        validate_network(config)


def test_duplicate_json_and_invalid_encoding_fail(tmp_path):
    path = tmp_path / "network.json"
    path.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match="JSON"):
        load_network(path)
    path.write_bytes(b"\xff")
    with pytest.raises(ValueError):
        load_network(path)


def test_valid_empty_service_has_no_trips_and_explicit_empty_summaries(config):
    day = config["schedules"][0]
    day["trips"] = []
    day["feeds"][0]["service_ids"] = []
    raw = day["platforms"][0].copy()
    raw.pop("feed_id")
    raw["route_ids"] = tuple(raw["route_ids"])
    day["headways"] = summarize_headways((Platform(**raw),), ())
    assert validate_network(config).trips_for_date(date(2026, 10, 5)) == ()


def test_required_rem_credit_cannot_be_replaced_by_arbitrary_text(config):
    config["attribution"] = ["Unrelated text"]
    for day in config["schedules"]:
        day["attribution"] = ["Unrelated text"]
    with pytest.raises(ValueError, match="REM attribution"):
        validate_network(config)


def test_missing_daily_credit_is_a_validation_error(config):
    config["schedules"][0]["attribution"] = None
    with pytest.raises(ValueError, match="attribution"):
        validate_network(config)
