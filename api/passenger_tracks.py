"""Build map-positioned passenger tracks for the station-view API.

Walk and corridor timestamps are seconds relative to the scenario start.
"""

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence

from api.station_layout import Connection, Corridor, Platform, Point
from simulator.engine.events import EventType
from simulator.passengers.transfer_component import TransferComponent


def build_passenger_tracks(
    records: Sequence[dict[str, object]],
    transfers: TransferComponent,
    connection: Connection,
    platforms: Mapping[str, Platform],
    corridors: Sequence[Corridor],
    duration_s: float,
) -> list[dict[str, object]]:
    """Convert event timestamps and walk records to map-position samples.

    Event records supply passenger state changes; immutable walk history supplies
    the group and corridor-arrival time even for unfinished walks at run end.
    Returned tracks are limited to the requested connection and run horizon.
    Sorting walk IDs keeps response ordering reproducible.
    Event records without a string passenger ID cannot be assigned to a track.
    A missing feeder alighting is treated as an absent path, not a guessed one.
    """
    events_by_passenger: dict[str, list[dict[str, object]]] = defaultdict(list)
    # Grouping once preserves event order while avoiding a full-log scan per walk.
    for record in records:
        passenger_id = record.get("passenger_id")
        if isinstance(passenger_id, str):
            events_by_passenger[passenger_id].append(record)
    corridor = next(item for item in corridors if item.id == connection.corridor_id)
    path_points = _movement_path(
        platforms[connection.from_platform_id],
        platforms[connection.to_platform_id],
        corridor,
    )
    tracks = []
    for passenger_id, walk in sorted(transfers.walk_records().items()):
        passenger_events = events_by_passenger[passenger_id]
        alighting = _source_alighting(passenger_events, connection.from_platform_id)
        if alighting is None:
            continue
        samples = _walk_samples(
            path_points, float(alighting["time_s"]), walk.corridor_arrival_s, duration_s
        )
        _append_corridor_samples(
            samples, passenger_id, transfers, path_points[-1], duration_s
        )
        _append_arrival_and_terminal_samples(
            samples, passenger_events, path_points[-1], platforms, duration_s
        )
        tracks.append(
            {
                "passenger_id": passenger_id,
                "group_id": walk.group_id,
                "connection_id": connection.id,
                "samples": samples,
            }
        )
    return tracks


def _source_alighting(
    records: Sequence[dict[str, object]], feeder_platform_id: str
) -> dict[str, object] | None:
    """Find the initial train alighting that begins a connection's walk.

    The feeder platform prevents unrelated passenger alightings from starting
    this connection's track; the relative timestamp anchors its first sample.
    Passengers without that event are omitted rather than given a false origin.
    """
    return next(
        (
            record
            for record in records
            if record.get("event_type") == EventType.ALIGHTING.value
            and record.get("platform_id") == feeder_platform_id
        ),
        None,
    )


def _movement_path(
    source: Platform, target: Platform, corridor: Corridor
) -> tuple[Point, ...]:
    """Join platform centers to the ordered corridor path.

    The corridor is oriented from the feeder to the connecting platform.
    Consecutive duplicates are removed to prevent zero-length interpolation spans.
    """
    candidates = (source.position, *corridor.path, target.position)
    points = []
    for point in candidates:
        if not points or point != points[-1]:
            points.append(point)
    return tuple(points)


def _walk_samples(
    points: Sequence[Point], start_s: float, end_s: float, duration_s: float
) -> list[dict[str, object]]:
    """Sample the exact walking interval, clipping unfinished walks at run end.

    The interpolation uses map-path distance as a fraction of the walk time.
    Degenerate paths stay at their origin, and out-of-run endpoints are clipped.
    Intermediate samples follow the geometry's ordered corridor points.
    """
    if end_s <= start_s:
        return [
            {
                "time_s": start_s,
                "position": _point_record(points[0]),
                "phase": "walking",
            }
        ]
    lengths = [
        math.hypot(second.x - first.x, second.y - first.y)
        for first, second in zip(points, points[1:], strict=False)
    ]
    total_length = math.fsum(lengths)
    if total_length <= 0:
        # A collapsed geometry has no meaningful segment to interpolate.
        return [
            {
                "time_s": start_s,
                "position": _point_record(points[0]),
                "phase": "walking",
            }
        ]
    samples: list[dict[str, object]] = []
    elapsed_length = 0.0
    _append_sample(samples, start_s, points[0], "walking", duration_s)
    for point, segment_length in zip(points[1:], lengths, strict=True):
        elapsed_length += segment_length
        time_s = start_s + (end_s - start_s) * elapsed_length / total_length
        if time_s > duration_s:
            # Later corridor points also occur after the horizon.
            break
        _append_sample(samples, time_s, point, "walking", duration_s)
    if end_s > duration_s and duration_s > start_s:
        fraction = (duration_s - start_s) / (end_s - start_s)
        # Place an unfinished passenger exactly where the run stops.
        _append_sample(
            samples,
            duration_s,
            _point_at(points, lengths, total_length, fraction),
            "walking",
            duration_s,
        )
    return samples


def _append_corridor_samples(
    samples: list[dict[str, object]],
    passenger_id: str,
    transfers: TransferComponent,
    corridor_end: Point,
    duration_s: float,
) -> None:
    """Record corridor queueing or passage at the simulation horizon.

    Queue delay is distinct from walking time and keeps passengers at the corridor.
    A passenger whose passage extends past the run remains queued at its end.
    """
    passage = transfers.passages.get(passenger_id)
    if passage is None:
        return
    if passage.arrival_s <= duration_s:
        # Arrival marks the corridor end; queue delay holds this position.
        phase = "queued" if passage.queue_delay_s > 0 else "walking"
        _append_sample(samples, passage.arrival_s, corridor_end, phase, duration_s)
    if passage.passage_s > duration_s and passage.arrival_s <= duration_s:
        _append_sample(samples, duration_s, corridor_end, "queued", duration_s)


def _append_arrival_and_terminal_samples(
    samples: list[dict[str, object]],
    records: Sequence[dict[str, object]],
    corridor_end: Point,
    platforms: Mapping[str, Platform],
    duration_s: float,
) -> None:
    """Record platform waiting and the first boarding or missed connection.

    Terminal position is taken from the event platform when available.
    All events are appended in event-log order and clipped to the run horizon.
    """
    arrival = next(
        (
            record
            for record in records
            if record.get("event_type") == EventType.PASSENGER_ARRIVAL.value
        ),
        None,
    )
    if arrival is not None:
        _append_sample(
            samples,
            float(arrival["time_s"]),
            platforms[str(arrival["platform_id"])].position,
            "waiting",
            duration_s,
        )
    terminal = next(
        (
            record
            for record in records
            if record.get("event_type")
            in {EventType.BOARDING.value, EventType.MISSED_CONNECTION.value}
        ),
        None,
    )
    if terminal is not None:
        terminal_platform = platforms.get(str(terminal["platform_id"]))
        # Destination alighting may have no map platform in this interchange.
        position = terminal_platform.position if terminal_platform else corridor_end
        phase = (
            "boarded"
            if terminal["event_type"] == EventType.BOARDING.value
            else "missed"
        )
        _append_sample(samples, float(terminal["time_s"]), position, phase, duration_s)


def _point_at(
    points: Sequence[Point],
    lengths: Sequence[float],
    total_length: float,
    fraction: float,
) -> Point:
    """Interpolate a point at a fraction of the full map path's distance.

    ``fraction`` is clamped to path bounds before selecting its segment.
    Segment lengths and coordinates use the same map-pixel units.
    """
    target_length = min(max(fraction, 0.0), 1.0) * total_length
    covered = 0.0
    for first, second, segment_length in zip(
        points[:-1], points[1:], lengths, strict=True
    ):
        if target_length <= covered + segment_length:
            part = (target_length - covered) / segment_length
            return Point(
                x=first.x + (second.x - first.x) * part,
                y=first.y + (second.y - first.y) * part,
            )
        covered += segment_length
    return points[-1]


def _append_sample(
    samples: list[dict[str, object]],
    time_s: float,
    position: Point,
    phase: str,
    duration_s: float,
) -> None:
    """Append one valid sample, replacing an earlier state at the same instant.

    Out-of-horizon event records are ignored so every returned track is bounded.
    The later state wins when two simulator events share a timestamp.
    """
    if not 0 <= time_s <= duration_s:
        return
    sample = {
        "time_s": float(time_s),
        "position": _point_record(position),
        "phase": phase,
    }
    if samples and samples[-1]["time_s"] == time_s:
        # Prefer the newer phase when same-time events update passenger state.
        samples[-1] = sample
    else:
        samples.append(sample)


def _point_record(point: Point) -> dict[str, float]:
    """Serialize a map coordinate without changing the validated point.

    Coordinates remain in the static layout's pixel units.
    """
    return {"x": point.x, "y": point.y}
