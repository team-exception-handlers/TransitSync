# AI contribution: 50% or more AI-generated
"""Read dated timetables from Supabase (#88)."""

import argparse
import json
import logging
from dataclasses import asdict
from datetime import date
from pathlib import Path

import psycopg

from scripts.extraction_logging import configure_logging
from scripts.gtfs_schedule import extract_trips
from scripts.supabase_calendar import (
    SupabaseReadError,
    _load_local_connection_settings,
    _read_calendar,
)
from scripts.supabase_connection import read_only_connection
from simulator.network_config import REM_ATTRIBUTION
from simulator.timetable import Platform, require_text

logger = logging.getLogger(__name__)

MAPPING_ROOT = Path(__file__).resolve().parents[1] / "config"
DEFAULT_MAPPING = MAPPING_ROOT / "interchange_mapping.json"
FEED_QUERY = """
SELECT feed_id, agency, feed_version, downloaded_on, feed_start_date, feed_end_date
FROM gtfs.feeds WHERE feed_id = %s
"""
ROUTES_QUERY = """
SELECT feed_id, route_id, route_type FROM gtfs.routes WHERE feed_id = %s
"""
STOPS_QUERY = """
SELECT feed_id, stop_id, stop_name, location_type FROM gtfs.stops WHERE feed_id = %s
"""
TRIPS_QUERY = """
SELECT feed_id, trip_id, service_id, route_id, direction_id, trip_headsign
FROM gtfs.trips WHERE feed_id = %s AND service_id = ANY(%s)
AND route_id = ANY(%s) ORDER BY trip_id
"""
STOP_TIMES_QUERY = """
SELECT feed_id, trip_id, stop_sequence, stop_id, arrival_s, departure_s,
       pickup_type, drop_off_type
FROM gtfs.stop_times WHERE feed_id = %s AND trip_id = ANY(%s)
ORDER BY trip_id, stop_sequence
"""
FREQUENCIES_QUERY = """
SELECT trip_id FROM gtfs.frequencies WHERE feed_id = %s AND trip_id = ANY(%s)
LIMIT 1
"""


def _unique_fields(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("mapping: duplicate JSON field")
        result[key] = value
    return result


def _contained_mapping_path(path: Path) -> Path:
    """Resolve the mapping path and reject anything outside MAPPING_ROOT."""
    root = MAPPING_ROOT.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"mapping must be inside the {root.name}/ folder")
    return resolved


def _mapping_platform(feed_id: str, row: object) -> Platform:
    """Build one Platform from a mapping row, naming the feed on failure."""
    if not isinstance(row, dict) or not isinstance(row.get("route_ids"), list):
        raise ValueError(f"mapping {feed_id!r}: route_ids must be a list")
    try:
        return Platform(**(row | {"route_ids": tuple(row["route_ids"])}))
    except (TypeError, KeyError, ValueError):
        raise ValueError(f"mapping {feed_id!r}: invalid platform fields") from None


def load_mapping(path: Path) -> dict[str, tuple[Platform, ...]]:
    """Load and validate feed-to-platform mappings."""
    path = _contained_mapping_path(path)
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_fields
        )
    except (OSError, UnicodeError, ValueError):
        raise ValueError("mapping: could not read a valid UTF-8 JSON mapping") from None
    if not isinstance(raw, dict) or not raw:
        raise ValueError("mapping must be a non-empty feed-to-platform object")
    raw.pop("$comment", None)
    if not raw:
        raise ValueError("mapping must contain at least one feed")
    result = {}
    seen = set()
    for feed_id, rows in raw.items():
        require_text(feed_id, "mapping feed_id")
        if not isinstance(rows, list) or not rows:
            raise ValueError("mapping feed must have a non-empty platform list")
        platforms = []
        for row in rows:
            platform = _mapping_platform(feed_id, row)
            if platform.platform_id in seen:
                raise ValueError("mapping: platform_id must be unique across feeds")
            seen.add(platform.platform_id)
            platforms.append(platform)
        result[feed_id] = tuple(sorted(platforms, key=lambda p: p.platform_id))
    return result


def _read_feed(connection, feed_id, platforms, service_date) -> tuple[dict, tuple]:
    services = _read_calendar(connection, feed_id, service_date)
    if not services:
        raise ValueError(
            f"feed {feed_id!r}, service_date {service_date}: "
            "no active services for extraction"
        )
    feed = connection.execute(FEED_QUERY, (feed_id,)).fetchone()
    require_text(feed.get("feed_version"), "feed_version")
    require_text(feed.get("agency"), "agency")
    if type(feed.get("downloaded_on")) is not date:
        raise ValueError("downloaded_on must be a date")
    routes = connection.execute(ROUTES_QUERY, (feed_id,)).fetchall()
    stops = connection.execute(STOPS_QUERY, (feed_id,)).fetchall()
    route_ids = sorted({r for p in platforms for r in p.route_ids})
    trips = connection.execute(
        TRIPS_QUERY, (feed_id, list(services), route_ids)
    ).fetchall()
    trip_ids = [row["trip_id"] for row in trips]
    if connection.execute(FREQUENCIES_QUERY, (feed_id, trip_ids)).fetchone():
        raise ValueError(f"feed {feed_id!r}: frequencies require separate expansion")
    stop_times = connection.execute(STOP_TIMES_QUERY, (feed_id, trip_ids)).fetchall()
    retained = extract_trips(
        feed_id=feed_id,
        service_ids=services,
        platforms=platforms,
        routes=routes,
        stops=stops,
        trips=trips,
        stop_times=stop_times,
    )
    metadata = {
        "feed_id": feed_id,
        "agency": feed["agency"],
        "feed_version": feed["feed_version"],
        "downloaded_on": feed["downloaded_on"].isoformat(),
        "coverage_start": feed["feed_start_date"].isoformat(),
        "coverage_end": feed["feed_end_date"].isoformat(),
        "service_ids": list(services),
    }
    return metadata, retained


def _daily_preview(connection, mappings, service_date) -> dict:
    feeds, trips = [], []
    for feed_id, platforms in sorted(mappings.items()):
        logger.info("Reading timetable: feed=%r service_date=%s", feed_id, service_date)
        feed, retained = _read_feed(connection, feed_id, platforms, service_date)
        logger.info(
            "Timetable read completed: feed=%r service_date=%s trips=%d",
            feed_id,
            service_date,
            len(retained),
        )
        feeds.append(feed)
        trips.extend(trip.to_dict() for trip in retained)
    return {
        "preview_schema_version": 1,
        "service_date": service_date.isoformat(),
        "timezone": "America/Toronto",
        "feeds": feeds,
        "attribution": [REM_ATTRIBUTION]
        if any(feed["agency"].upper() == "REM" for feed in feeds)
        else [],
        "platforms": [
            asdict(p) | {"feed_id": feed, "route_ids": list(p.route_ids)}
            for feed in sorted(mappings)
            for p in sorted(mappings[feed], key=lambda p: p.platform_id)
        ],
        "trips": trips,
    }


def read_schedules(mappings, service_dates: tuple[date, ...]) -> list[dict]:
    """Read feeds and dates in one read-only snapshot."""
    if (
        not service_dates
        or any(type(d) is not date for d in service_dates)
        or len(set(service_dates)) != len(service_dates)
    ):
        raise ValueError("service_dates must contain unique datetime.date values")
    _check_mappings(mappings)
    try:
        with read_only_connection() as connection:
            return [_daily_preview(connection, mappings, day) for day in service_dates]
    except psycopg.Error:
        logger.error(
            "Timetable read failed: feeds=%r service_dates=%s",
            sorted(mappings),
            ",".join(day.isoformat() for day in service_dates),
        )
        raise SupabaseReadError(
            "Could not read Supabase timetable. Check connection, TLS and SELECT "
            "permissions, including repaired pickup_type/drop_off_type columns."
        ) from None


def read_daily_schedule(mappings, service_date: date) -> dict:
    """Read one date using connection settings from the environment."""
    if type(service_date) is not date:
        raise ValueError("service_date must be a datetime.date without a time")
    return read_schedules(mappings, (service_date,))[0]


def _check_feed_platforms(feed_id, platforms, seen: set[str]) -> None:
    """Validate one feed's platforms, adding their IDs to the shared seen set."""
    if require_text(feed_id, "feed_id") != feed_id:
        raise ValueError("feed_id must not have surrounding whitespace")
    if not isinstance(platforms, tuple) or not platforms:
        raise ValueError("platforms must be a non-empty tuple")
    for platform in platforms:
        if not isinstance(platform, Platform):
            raise ValueError("platforms must contain Platform values")
        if platform.platform_id in seen:
            raise ValueError("platform_id must be unique across mapped feeds")
        seen.add(platform.platform_id)


def _check_mappings(mappings) -> None:
    if not isinstance(mappings, dict) or not mappings:
        raise ValueError("mappings must contain at least one feed")
    seen: set[str] = set()
    for feed_id, platforms in mappings.items():
        _check_feed_platforms(feed_id, platforms, seen)


def main(argv: list[str] | None = None) -> int:
    """Print a daily JSON preview or a sanitized error."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    args = parser.parse_args(argv)
    configure_logging()
    try:
        mappings = load_mapping(args.mapping)
        _load_local_connection_settings()
        result = read_daily_schedule(mappings, args.date)
    except (ValueError, SupabaseReadError) as error:
        logger.error("Timetable command failed: service_date=%s: %s", args.date, error)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
