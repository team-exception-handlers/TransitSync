# AI contribution: 50% or more AI-generated
"""Train schedule records and headway calculations.

Times are stored as seconds: GTFS 25:00 becomes 90,000 seconds.
Passenger-service checks tell us whether a journey is possible, not how many
passengers take it. Schedule records cannot be changed after creation.
"""

from dataclasses import asdict, dataclass


def require_text(value: object, field: str) -> str:
    """Return stripped, nonempty text."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def require_integer(value: object, field: str, minimum: int = 0) -> int:
    """Require an integer >= minimum; reject bool."""
    if type(value) is not int or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class Platform:
    """An interchange platform for one line and direction."""

    platform_id: str
    interchange_id: str
    line_id: str
    direction_id: int
    direction_label: str
    stop_id: str
    stop_name: str
    route_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in (
            "platform_id",
            "interchange_id",
            "line_id",
            "direction_label",
            "stop_id",
            "stop_name",
        ):
            value = require_text(getattr(self, field), field)
            object.__setattr__(self, field, value)
        if type(self.direction_id) is not int or self.direction_id not in (0, 1):
            raise ValueError("direction_id must be 0 or 1")
        if not isinstance(self.route_ids, tuple) or not self.route_ids:
            raise ValueError("route_ids must be a non-empty tuple")
        routes = tuple(require_text(r, "route_id") for r in self.route_ids)
        if len(set(routes)) != len(routes):
            raise ValueError("route_ids must be unique")
        object.__setattr__(self, "route_ids", tuple(sorted(routes)))


@dataclass(frozen=True, slots=True, kw_only=True)
class ScheduledVisit:
    """A timed stop with permissions and full-trip service context."""

    platform_id: str
    stop_id: str
    stop_sequence: int
    arrival_s: int
    departure_s: int
    pickup_type: int
    drop_off_type: int
    has_earlier_boarding: bool
    has_later_alighting: bool

    def __post_init__(self) -> None:
        require_text(self.platform_id, "platform_id")
        require_text(self.stop_id, "stop_id")
        for field in ("stop_sequence", "arrival_s", "departure_s"):
            require_integer(getattr(self, field), field)
        if self.departure_s < self.arrival_s:
            raise ValueError("departure_s must be >= arrival_s")
        for field in ("pickup_type", "drop_off_type"):
            if type(getattr(self, field)) is not int or getattr(self, field) not in (
                0,
                1,
            ):
                raise ValueError(
                    f"{field}: this timetable supports regular/prohibited service"
                )
        for field in ("has_earlier_boarding", "has_later_alighting"):
            if type(getattr(self, field)) is not bool:
                raise ValueError(f"{field} must be a boolean")

    @property
    def boarding_allowed(self) -> bool:
        """Whether regular boarding is allowed here."""
        return self.pickup_type == 0

    @property
    def alighting_allowed(self) -> bool:
        """Whether regular alighting is allowed here."""
        return self.drop_off_type == 0

    @property
    def incoming_passenger_service(self) -> bool:
        """Whether passengers can alight after boarding earlier on this trip."""
        return self.alighting_allowed and self.has_earlier_boarding

    @property
    def outgoing_passenger_service(self) -> bool:
        """Whether passengers can board and alight later on this trip."""
        return self.boarding_allowed and self.has_later_alighting

    def to_dict(self) -> dict:
        """Serialize the visit, including local permissions."""
        return asdict(self) | {
            "boarding_allowed": self.boarding_allowed,
            "alighting_allowed": self.alighting_allowed,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ScheduledTrip:
    """One source trip and its ordered interchange visits."""

    feed_id: str
    trip_id: str
    service_id: str
    route_id: str
    direction_id: int
    destination: str
    visits: tuple[ScheduledVisit, ...]

    def __post_init__(self) -> None:
        for field in ("feed_id", "trip_id", "service_id", "route_id", "destination"):
            require_text(getattr(self, field), field)
        if type(self.direction_id) is not int or self.direction_id not in (0, 1):
            raise ValueError("direction_id must be 0 or 1")
        if not isinstance(self.visits, tuple) or not self.visits:
            raise ValueError("visits must be a non-empty tuple")
        if not all(isinstance(v, ScheduledVisit) for v in self.visits):
            raise ValueError("visits must contain ScheduledVisit values")
        for previous, current in zip(self.visits, self.visits[1:], strict=False):
            if (
                current.stop_sequence <= previous.stop_sequence
                or current.arrival_s < previous.departure_s
            ):
                raise ValueError(
                    "visits must have increasing sequence and chronological times"
                )

    def to_dict(self) -> dict:
        """Serialize the trip and its visits."""
        return {
            "feed_id": self.feed_id,
            "trip_id": self.trip_id,
            "service_id": self.service_id,
            "route_id": self.route_id,
            "direction_id": self.direction_id,
            "destination": self.destination,
            "visits": [visit.to_dict() for visit in self.visits],
        }


TIME_BANDS = ("early", "am", "midday", "pm", "evening", "late")
BAND_STARTS_S = (6 * 3600, 9 * 3600, 15 * 3600, 18 * 3600, 21 * 3600)


def _headway_bands(departures: list[int]) -> list[dict]:
    from bisect import bisect_right
    from statistics import median

    times = [[] for _ in TIME_BANDS]
    gaps = [[] for _ in TIME_BANDS]
    ordered = sorted(departures)
    for index, departure in enumerate(ordered):
        band = bisect_right(BAND_STARTS_S, departure)
        times[band].append(departure)
        if index:
            gaps[band].append(departure - ordered[index - 1])
    return [
        {
            "band": name,
            "departure_s": times[index],
            "departure_count": len(times[index]),
            "gap_count": len(gaps[index]),
            "median_s": median(gaps[index]) if gaps[index] else None,
            "min_s": min(gaps[index]) if gaps[index] else None,
            "max_s": max(gaps[index]) if gaps[index] else None,
        }
        for index, name in enumerate(TIME_BANDS)
    ]


def summarize_headways(
    platforms: tuple[Platform, ...],
    trips: tuple[ScheduledTrip, ...],
) -> list[dict]:
    """Summarize boarding-eligible departures by route and platform.

    Preserve simultaneous trains and empty groups. Assign gaps to the later
    departure's band within each day. Combined service may have different destinations.
    """
    times = {(p.platform_id, route): [] for p in platforms for route in p.route_ids}
    for trip in trips:
        for visit in trip.visits:
            key = (visit.platform_id, trip.route_id)
            if key not in times:
                raise ValueError("headways: trip refers to an unmapped platform/route")
            if visit.outgoing_passenger_service:
                times[key].append(visit.departure_s)
    summaries = []
    for platform in sorted(platforms, key=lambda p: p.platform_id):
        combined = []
        for route in platform.route_ids:
            departures = times[(platform.platform_id, route)]
            combined.extend(departures)
            summaries.append(
                {
                    "platform_id": platform.platform_id,
                    "route_id": route,
                    "scope": "route",
                    "bands": _headway_bands(departures),
                }
            )
        summaries.append(
            {
                "platform_id": platform.platform_id,
                "route_id": None,
                "scope": "combined_platform",
                "bands": _headway_bands(combined),
            }
        )
    return summaries
