# AI contribution: 50% or more AI-generated
"""Validate and load reference schedules offline."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlsplit

from simulator.timetable import (
    Platform,
    ScheduledTrip,
    ScheduledVisit,
    require_text,
    summarize_headways,
)

REM_ATTRIBUTION = (
    "Schedule data from the Réseau express métropolitain (REM), https://rem.info, "
    "used under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). "
    "Data has been processed and modified for this project."
)


def _fields(value, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label}: missing or unknown fields")


def _list(value, label: str, *, nonempty=False) -> list:
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f"{label}: expected {'nonempty ' if nonempty else ''}list")
    return value


def _date(value, label: str) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError(f"{label}: expected YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{label}: invalid date") from None


def _texts(value, label: str) -> tuple[str, ...]:
    values = tuple(require_text(v, label) for v in _list(value, label))
    if len(values) != len(set(values)):
        raise ValueError(f"{label}: duplicate values")
    return values


@dataclass(frozen=True, slots=True)
class NetworkConfig:
    """Immutable platforms and timetables for extracted dates only."""

    reference_dates: Mapping[str, date]
    platforms: tuple[Platform, ...]
    schedules: Mapping[date, tuple[ScheduledTrip, ...]]
    platform_feed_ids: Mapping[str, str]

    def trips_for_date(self, service_date: date) -> tuple[ScheduledTrip, ...]:
        if type(service_date) is not date:
            raise ValueError("service_date must be a datetime.date without a time")
        if service_date not in self.schedules:
            raise ValueError(
                f"service_date {service_date}: not extracted in this config"
            )
        return self.schedules[service_date]


def _feeds(day: dict) -> dict[str, dict]:
    feeds = {}
    service_date = _date(day.get("service_date"), "service_date")
    for feed in _list(day.get("feeds"), "feeds", nonempty=True):
        _fields(
            feed,
            {
                "feed_id",
                "agency",
                "feed_version",
                "downloaded_on",
                "coverage_start",
                "coverage_end",
                "service_ids",
            },
            "feed",
        )
        for field in ("feed_id", "agency", "feed_version"):
            require_text(feed[field], field)
        if feed["feed_id"] in feeds:
            raise ValueError("feeds: duplicate feed_id")
        start = _date(feed["coverage_start"], "coverage_start")
        end = _date(feed["coverage_end"], "coverage_end")
        if not start <= service_date <= end:
            raise ValueError("feed coverage does not include extracted service_date")
        _date(feed["downloaded_on"], "downloaded_on")
        _texts(feed["service_ids"], "service_ids")
        feeds[feed["feed_id"]] = feed
    return feeds


def _platforms(day, feeds):
    platforms, platform_feeds = {}, {}
    for row in _list(day.get("platforms"), "platforms", nonempty=True):
        _fields(
            row,
            {
                "feed_id",
                "platform_id",
                "interchange_id",
                "line_id",
                "direction_id",
                "direction_label",
                "stop_id",
                "stop_name",
                "route_ids",
            },
            "platform",
        )
        feed_id = row["feed_id"]
        if not isinstance(feed_id, str) or feed_id not in feeds:
            raise ValueError("platform: unknown feed_id")
        values = {key: value for key, value in row.items() if key != "feed_id"}
        values["route_ids"] = _texts(values["route_ids"], "route_ids")
        platform = Platform(**values)
        if platform.platform_id != row["platform_id"]:
            raise ValueError("platform_id must not have surrounding whitespace")
        if platform.platform_id in platforms:
            raise ValueError("platform: duplicate platform_id")
        platforms[platform.platform_id] = platform
        platform_feeds[platform.platform_id] = feed_id
    return platforms, platform_feeds


def _visit(row, trip, platforms, platform_feeds) -> ScheduledVisit:
    fields = {
        "platform_id",
        "stop_id",
        "stop_sequence",
        "arrival_s",
        "departure_s",
        "pickup_type",
        "drop_off_type",
        "has_earlier_boarding",
        "has_later_alighting",
    }
    _fields(row, fields | {"boarding_allowed", "alighting_allowed"}, "visit")
    visit = ScheduledVisit(**{key: row[key] for key in fields})
    for field in ("boarding_allowed", "alighting_allowed"):
        if type(row[field]) is not bool or row[field] != getattr(visit, field):
            raise ValueError(f"visit: inconsistent {field}")
    platform = platforms.get(visit.platform_id)
    if platform is None or (
        platform_feeds[visit.platform_id] != trip["feed_id"]
        or platform.stop_id != visit.stop_id
        or platform.direction_id != trip["direction_id"]
        or trip["route_id"] not in platform.route_ids
    ):
        raise ValueError("visit: platform/feed/route/direction/stop mismatch")
    return visit


def parse_timetable(
    day: dict,
) -> tuple[tuple[Platform, ...], tuple[ScheduledTrip, ...]]:
    """Validate and reconstruct a saved or preview timetable."""
    feeds = _feeds(day)
    platforms, platform_feeds = _platforms(day, feeds)
    trips, seen = [], set()
    fields = {
        "feed_id",
        "trip_id",
        "service_id",
        "route_id",
        "direction_id",
        "destination",
    }
    for row in _list(day.get("trips"), "trips"):
        _fields(row, fields | {"visits"}, "trip")
        for field in fields - {"direction_id"}:
            require_text(row[field], field)
        feed = feeds.get(row["feed_id"])
        if feed is None or row["service_id"] not in feed["service_ids"]:
            raise ValueError("trip: unknown feed/service")
        key = (row["feed_id"], row["trip_id"])
        if key in seen:
            raise ValueError("trip: duplicate feed_id/trip_id")
        seen.add(key)
        visits = tuple(
            _visit(v, row, platforms, platform_feeds)
            for v in _list(row["visits"], "visits", nonempty=True)
        )
        trips.append(ScheduledTrip(**{key: row[key] for key in fields}, visits=visits))
    return tuple(sorted(platforms.values(), key=lambda p: p.platform_id)), tuple(trips)


def _map_evidence(rows) -> None:
    for row in _list(rows, "map_evidence", nonempty=True):
        _fields(row, {"url", "checked_on", "notes"}, "map_evidence")
        url = urlsplit(require_text(row["url"], "map_evidence.url"))
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "map_evidence: expected public HTTPS URL without credentials"
            )
        _date(row["checked_on"], "map_evidence.checked_on")
        require_text(row["notes"], "map_evidence.notes")


def _references(raw: dict) -> dict[str, date]:
    _fields(
        raw,
        {
            "schema_version",
            "kind",
            "timezone",
            "reference_dates",
            "schedules",
            "map_evidence",
            "attribution",
        },
        "network",
    )
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValueError("schema_version: unsupported network config")
    if (
        raw["kind"] != "representative_schedules"
        or raw["timezone"] != "America/Toronto"
    ):
        raise ValueError("kind/timezone: unsupported representative config")
    _fields(
        raw["reference_dates"], {"weekday", "saturday", "sunday"}, "reference_dates"
    )
    references = {
        name: _date(value, "reference_dates")
        for name, value in raw["reference_dates"].items()
    }
    if (
        references["weekday"].weekday() > 4
        or references["saturday"].weekday() != 5
        or references["sunday"].weekday() != 6
    ):
        raise ValueError("reference_dates: labels must match calendar weekdays")
    _map_evidence(raw["map_evidence"])
    if not _texts(raw["attribution"], "attribution"):
        raise ValueError("attribution must not be empty")
    return references


def _checked_schedule(day: dict, attribution: list):
    _fields(
        day,
        {
            "service_date",
            "timezone",
            "feeds",
            "platforms",
            "trips",
            "attribution",
            "headways",
        },
        "schedule",
    )
    if day["timezone"] != "America/Toronto":
        raise ValueError("schedule timezone mismatch")
    service_date = _date(day["service_date"], "service_date")
    platforms, trips = parse_timetable(day)
    credits = _texts(day["attribution"], "attribution")
    if (
        any(feed["agency"].upper() == "REM" for feed in day["feeds"])
        and REM_ATTRIBUTION not in credits
    ):
        raise ValueError("REM attribution: required source credit is missing")
    expected = summarize_headways(platforms, trips)
    if json.dumps(day["headways"], sort_keys=True, allow_nan=False) != json.dumps(
        expected, sort_keys=True
    ):
        raise ValueError("headways: saved summaries disagree with visits")
    if not set(credits).issubset(attribution):
        raise ValueError("schedule attribution missing from config")
    source = sorted(
        (
            f["feed_id"],
            f["agency"],
            f["feed_version"],
            f["downloaded_on"],
            f["coverage_start"],
            f["coverage_end"],
        )
        for f in day["feeds"]
    )
    mapping = dict(sorted((p["platform_id"], p["feed_id"]) for p in day["platforms"]))
    return service_date, platforms, trips, (source, mapping)


def validate_network(raw: dict) -> NetworkConfig:
    """Validate the saved config and return immutable records."""
    references = _references(raw)
    schedules, first_platforms, identities = {}, None, None
    for day in _list(raw["schedules"], "schedules", nonempty=True):
        service_date, platforms, trips, source = _checked_schedule(
            day, raw["attribution"]
        )
        if service_date in schedules:
            raise ValueError("schedules: duplicate service_date")
        if first_platforms is not None and (
            platforms != first_platforms or source != identities
        ):
            raise ValueError(
                "schedules: topology or source edition changes between dates"
            )
        first_platforms, identities = platforms, source
        schedules[service_date] = trips
    if set(schedules) != set(references.values()):
        raise ValueError("schedules must contain exactly the explicit reference_dates")
    return NetworkConfig(
        reference_dates=MappingProxyType(references),
        platforms=first_platforms,
        schedules=MappingProxyType(schedules),
        platform_feed_ids=MappingProxyType(identities[1]),
    )


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def load_network(path: Path) -> NetworkConfig:
    """Load and validate UTF-8 JSON offline."""
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_fields
        )
    except (OSError, UnicodeError, ValueError):
        raise ValueError("network config: could not read valid UTF-8 JSON") from None
    return validate_network(raw)
