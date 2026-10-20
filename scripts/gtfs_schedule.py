# AI contribution: 50% or more AI-generated
"""Extract interchange visits from complete GTFS trips (#88)."""

from collections import defaultdict
from collections.abc import Iterable, Mapping

from simulator.timetable import (
    Platform,
    ScheduledTrip,
    ScheduledVisit,
    require_integer,
    require_text,
)

type Row = Mapping[str, object]


def _index(rows: Iterable[Row], feed_id: str, field: str) -> dict[str, Row]:
    result = {}
    for row in rows:
        if row.get("feed_id") != feed_id:
            continue
        key = require_text(row.get(field), field)
        if key in result:
            raise ValueError(f"duplicate {field}: {key!r}")
        result[key] = row
    return result


def _platform_lookup(platforms, routes, stops) -> dict[tuple[str, int, str], Platform]:
    lookup = {}
    seen = set()
    for platform in platforms:
        if platform.platform_id in seen:
            raise ValueError("mapping: duplicate platform_id")
        seen.add(platform.platform_id)
        stop = stops.get(platform.stop_id)
        if stop is None or stop.get("stop_name") != platform.stop_name:
            raise ValueError(
                f"mapping {platform.platform_id}: stop_name/stop_id mismatch; "
                "check mapping"
            )
        if type(stop.get("location_type")) is not int or stop["location_type"] != 0:
            raise ValueError(
                f"mapping {platform.platform_id}: stop must be a passenger platform"
            )
        for route_id in platform.route_ids:
            route = routes.get(route_id)
            if (
                route is None
                or type(route.get("route_type")) is not int
                or route["route_type"] not in (0, 1)
            ):
                raise ValueError(
                    f"mapping {platform.platform_id}: missing or non-rail route"
                )
            key = (route_id, platform.direction_id, platform.stop_id)
            if key in lookup:
                raise ValueError("mapping: ambiguous route/direction/stop")
            lookup[key] = platform
    return lookup


def _checked_stops(rows: list[Row], stops: dict[str, Row]) -> list[Row]:
    sequences = set()
    for row in rows:
        sequence = require_integer(row.get("stop_sequence"), "stop_sequence")
        if sequence in sequences:
            raise ValueError("duplicate stop_sequence within source trip")
        sequences.add(sequence)
        stop_id = require_text(row.get("stop_id"), "stop_id")
        if stop_id != row["stop_id"]:
            raise ValueError("stop_id must not have surrounding whitespace")
        if stop_id not in stops:
            raise ValueError("stop_id: source trip refers to an unknown stop")
        arrival = require_integer(row.get("arrival_s"), "arrival_s")
        departure = require_integer(row.get("departure_s"), "departure_s")
        if departure < arrival:
            raise ValueError("departure_s must be >= arrival_s")
        for field in ("pickup_type", "drop_off_type"):
            value = row.get(field)
            if type(value) is not int or value not in (0, 1):
                raise ValueError(f"{field}: expected regular/prohibited permission")
    checked = sorted(rows, key=lambda row: row["stop_sequence"])
    for previous, current in zip(checked, checked[1:], strict=False):
        if current["arrival_s"] < previous["departure_s"]:
            raise ValueError("source trip stop_times must be chronological")
    return checked


def _retained_visits(
    trip: Row, rows: list[Row], lookup: dict
) -> tuple[ScheduledVisit, ...]:
    # Count only earlier/later stops, including those outside the modeled network.
    later = [False] * len(rows)
    opportunity = False
    for index in range(len(rows) - 1, -1, -1):
        later[index] = opportunity
        opportunity = opportunity or rows[index]["drop_off_type"] == 0
    visits = []
    earlier = False
    mapped_stops = {key[2] for key in lookup if key[0] == trip["route_id"]}
    for index, row in enumerate(rows):
        platform = lookup.get((trip["route_id"], trip["direction_id"], row["stop_id"]))
        if platform is None and row["stop_id"] in mapped_stops:
            raise ValueError("mapping: source stop/direction mismatch; check mapping")
        if platform is not None:
            visits.append(
                ScheduledVisit(
                    platform_id=platform.platform_id,
                    stop_id=row["stop_id"],
                    stop_sequence=row["stop_sequence"],
                    arrival_s=row["arrival_s"],
                    departure_s=row["departure_s"],
                    pickup_type=row["pickup_type"],
                    drop_off_type=row["drop_off_type"],
                    has_earlier_boarding=earlier,
                    has_later_alighting=later[index],
                )
            )
        earlier = earlier or row["pickup_type"] == 0
    return tuple(visits)


def extract_trips(
    *,
    feed_id: str,
    service_ids: Iterable[str],
    platforms: tuple[Platform, ...],
    routes: Iterable[Row],
    stops: Iterable[Row],
    trips: Iterable[Row],
    stop_times: Iterable[Row],
) -> tuple[ScheduledTrip, ...]:
    """Extract active interchange visits for one feed.

    Callers check calendars and coverage. Validate full trips before trimming;
    invalid data raises instead of producing empty service.
    """
    feed_id = require_text(feed_id, "feed_id")
    active = {require_text(s, "service_id") for s in service_ids}
    route_index = _index(routes, feed_id, "route_id")
    stop_index = _index(stops, feed_id, "stop_id")
    trip_index = _index(trips, feed_id, "trip_id")
    lookup = _platform_lookup(platforms, route_index, stop_index)
    selected = _selected_trips(trip_index, active, route_index, lookup)
    grouped = defaultdict(list)
    for row in stop_times:
        if row.get("feed_id") == feed_id and row.get("trip_id") in selected:
            grouped[row["trip_id"]].append(row)
    result = []
    for trip_id, trip in sorted(selected.items()):
        if not grouped[trip_id]:
            raise ValueError(f"trip {trip_id!r}: missing stop_times")
        try:
            rows = _checked_stops(grouped[trip_id], stop_index)
            visits = _retained_visits(trip, rows, lookup)
        except ValueError as error:
            raise ValueError(f"feed {feed_id!r}, trip {trip_id!r}: {error}") from error
        if visits:
            result.append(
                ScheduledTrip(
                    feed_id=feed_id,
                    trip_id=trip_id,
                    service_id=trip["service_id"],
                    route_id=trip["route_id"],
                    direction_id=trip["direction_id"],
                    destination=require_text(
                        trip.get("trip_headsign"), "trip_headsign"
                    ),
                    visits=visits,
                )
            )
    return tuple(result)


def _selected_trips(trips, active, routes, lookup) -> dict[str, Row]:
    selected = {}
    retained_routes = {key[0] for key in lookup}
    for trip_id, trip in trips.items():
        service = require_text(trip.get("service_id"), "service_id")
        if service not in active:
            continue
        route = require_text(trip.get("route_id"), "route_id")
        if route != trip["route_id"]:
            raise ValueError(
                f"trip {trip_id!r}: route_id must not have surrounding whitespace"
            )
        if route not in routes:
            raise ValueError(f"trip {trip_id!r}: unknown route_id")
        if route not in retained_routes:
            continue
        direction = trip.get("direction_id")
        if type(direction) is not int or direction not in (0, 1):
            raise ValueError(f"trip {trip_id!r}: direction_id must be 0 or 1")
        selected[trip_id] = trip
    return selected
