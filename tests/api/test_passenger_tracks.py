# AI contribution: 50% or more AI-generated
"""Hand-calculated passenger tracks along a transfer route (US-3.1, #65).

The route is an L shape 90 pixels long:

    feeder (0, 0) -> (10, 0) -> (10, 30) -> (40, 30) -> metro (60, 30)

The corridor is the three middle points, so its metro end, the bottleneck,
is (40, 30), 70 pixels from the feeder platform. Every walk below takes one
second per pixel, so each expected time is a running distance.
"""

from types import SimpleNamespace

from api.passenger_tracks import build_passenger_tracks
from api.station_layout import Connection, Corridor, Platform, Point
from simulator.passengers.corridor import CorridorPassage


def _platform(platform_id: str, x: float, y: float) -> Platform:
    """Return a platform whose only meaningful fields are its ID and position."""
    return Platform(
        platform_id=platform_id,
        interchange_id="fixture",
        line_id="rem",
        direction_id=0,
        direction_label=platform_id,
        stop_id=f"stop-{platform_id}",
        stop_name=platform_id,
        route_ids=["route"],
        station_id=f"station-{platform_id}",
        source_feed_id="fixture",
        position=Point(x=x, y=y),
        color="#000000",
    )


PLATFORMS = {"feeder": _platform("feeder", 0, 0), "metro": _platform("metro", 60, 30)}
CORRIDOR = Corridor(
    id="corridor",
    label="Corridor",
    from_platform_id="feeder",
    to_platform_id="metro",
    path=[Point(x=10, y=0), Point(x=10, y=30), Point(x=40, y=30)],
)
CONNECTION = Connection(
    id="feeder-metro",
    label="Feeder to metro",
    from_platform_id="feeder",
    to_platform_id="metro",
    corridor_id="corridor",
)


def _event(event_type: str, time_s: float, platform_id: str) -> dict[str, object]:
    """Return one passenger event record for the single test passenger."""
    return {
        "event_type": event_type,
        "passenger_id": "p1",
        "time_s": time_s,
        "platform_id": platform_id,
    }


def _track(
    corridor_arrival_s: float,
    passage: CorridorPassage | None,
    records: list[dict[str, object]],
    duration_s: float = 1000.0,
) -> list[tuple[float, tuple[float, float], str]]:
    """Build the one passenger's track and return (time, (x, y), phase) tuples."""
    transfers = SimpleNamespace(
        walk_records=lambda: {
            "p1": SimpleNamespace(group_id="g1", corridor_arrival_s=corridor_arrival_s)
        },
        passages={} if passage is None else {"p1": passage},
    )
    (track,) = build_passenger_tracks(
        records, transfers, CONNECTION, PLATFORMS, [CORRIDOR], duration_s
    )
    return [
        (
            sample["time_s"],
            (sample["position"]["x"], sample["position"]["y"]),
            sample["phase"],
        )
        for sample in track["samples"]
    ]


def test_unqueued_passenger_walks_the_whole_route_to_the_platform() -> None:
    """A 90 s walk follows every bend and ends on the metro platform."""
    passage = CorridorPassage("p1", arrival_s=190.0, passage_s=190.0, queue_delay_s=0)
    records = [
        _event("alighting", 100.0, "feeder"),
        _event("corridor_arrival", 190.0, "metro"),
        _event("passenger_arrival", 190.0, "metro"),
    ]

    assert _track(190.0, passage, records) == [
        (100.0, (0.0, 0.0), "walking"),
        (110.0, (10.0, 0.0), "walking"),
        (140.0, (10.0, 30.0), "walking"),
        (170.0, (40.0, 30.0), "walking"),
        (190.0, (60.0, 30.0), "waiting"),
    ]


def test_queued_passenger_waits_at_the_bottleneck_then_reaches_the_platform() -> None:
    """A 70 s walk to the bottleneck, a 5 s queue there, then the platform."""
    passage = CorridorPassage("p1", arrival_s=170.0, passage_s=175.0, queue_delay_s=5)
    records = [
        _event("alighting", 100.0, "feeder"),
        _event("corridor_arrival", 170.0, "metro"),
        _event("passenger_arrival", 175.0, "metro"),
        _event("boarding", 200.0, "metro"),
    ]

    assert _track(170.0, passage, records) == [
        (100.0, (0.0, 0.0), "walking"),
        (110.0, (10.0, 0.0), "walking"),
        (140.0, (10.0, 30.0), "walking"),
        (170.0, (40.0, 30.0), "queued"),
        (175.0, (60.0, 30.0), "waiting"),
        (200.0, (60.0, 30.0), "boarded"),
    ]


def test_passenger_still_queued_at_run_end_stays_at_the_bottleneck() -> None:
    """The run stops at 172 s, inside a queue that lasts until 180 s."""
    passage = CorridorPassage("p1", arrival_s=170.0, passage_s=180.0, queue_delay_s=10)
    records = [
        _event("alighting", 100.0, "feeder"),
        _event("corridor_arrival", 170.0, "metro"),
    ]

    track = _track(170.0, passage, records, duration_s=172.0)

    assert track[-2:] == [
        (170.0, (40.0, 30.0), "queued"),
        (172.0, (40.0, 30.0), "queued"),
    ]


def test_walk_cut_by_run_end_stops_at_the_right_point_on_the_route() -> None:
    """At 145 s a 90 s walk is half done: 45 px, 5 px past the second bend."""
    records = [_event("alighting", 100.0, "feeder")]

    assert _track(190.0, None, records, duration_s=145.0) == [
        (100.0, (0.0, 0.0), "walking"),
        (110.0, (10.0, 0.0), "walking"),
        (140.0, (10.0, 30.0), "walking"),
        (145.0, (15.0, 30.0), "walking"),
    ]
