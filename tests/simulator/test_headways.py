# AI contribution: 50% or more AI-generated
"""Headways, passenger eligibility and time-band boundaries."""

from dataclasses import replace

from simulator.timetable import (
    Platform,
    ScheduledTrip,
    ScheduledVisit,
    summarize_headways,
)

PLATFORM = Platform(
    platform_id="p",
    interchange_id="mcgill",
    line_id="rem",
    direction_id=0,
    direction_label="Outbound",
    stop_id="s",
    stop_name="McGill",
    route_ids=("S1", "S2"),
)


def train(identifier, departure, route="S1", **facts):
    visit = ScheduledVisit(
        platform_id="p",
        stop_id="s",
        stop_sequence=2,
        arrival_s=departure - 30,
        departure_s=departure,
        pickup_type=0,
        drop_off_type=0,
        has_earlier_boarding=True,
        has_later_alighting=True,
    )
    return ScheduledTrip(
        feed_id="f",
        trip_id=identifier,
        service_id="day",
        route_id=route,
        direction_id=0,
        destination="Destination",
        visits=(replace(visit, **facts),),
    )


def combined(trips):
    return next(
        s
        for s in summarize_headways((PLATFORM,), trips)
        if s["scope"] == "combined_platform"
    )


def test_gaps_cross_bands_and_use_later_departure_band():
    summary = combined((train("a", 21540), train("b", 21660), train("c", 21900)))
    bands = {b["band"]: b for b in summary["bands"]}
    assert bands["early"]["departure_count"] == 1
    assert bands["early"]["gap_count"] == 0
    assert bands["early"]["median_s"] is None
    # 06:01 - 05:59 = 120; 06:05 - 06:01 = 240; median = 180.
    assert bands["am"]["departure_s"] == [21660, 21900]
    assert (bands["am"]["min_s"], bands["am"]["median_s"], bands["am"]["max_s"]) == (
        120,
        180,
        240,
    )
    assert bands["midday"]["departure_count"] == 0
    assert bands["midday"]["median_s"] is None


def test_exact_boundaries_and_overnight_seconds_are_not_wrapped():
    departures = [21600, 32400, 54000, 64800, 75600, 90000]
    summary = combined(tuple(train(str(i), d) for i, d in enumerate(departures)))
    assert [b["departure_count"] for b in summary["bands"]] == [0, 1, 1, 1, 1, 2]
    assert summary["bands"][-1]["departure_s"] == [75600, 90000]
    assert summary["bands"][-1]["max_s"] == 14400


def test_ineligible_physical_departures_do_not_improve_boarding_frequency():
    summary = combined(
        (
            train("a", 28800),
            train("b", 29100, pickup_type=1),
            train("c", 29400),
            train("d", 29700, has_later_alighting=False),
        )
    )
    am = summary["bands"][1]
    assert am["departure_count"] == 2
    assert am["median_s"] == 600


def test_routes_are_separate_and_identical_distinct_trains_are_preserved():
    trips = (train("a", 28800), train("b", 28800, "S2"), train("c", 29400))
    summaries = summarize_headways((PLATFORM,), tuple(reversed(trips)))
    route = next(s for s in summaries if s["route_id"] == "S1")
    assert route["bands"][1]["median_s"] == 600
    assert combined(trips)["bands"][1]["median_s"] == 300
    assert combined(trips)["bands"][1]["min_s"] == 0
    assert summaries == summarize_headways((PLATFORM,), trips)


def test_no_service_has_explicit_empty_bands_for_every_mapped_route():
    summaries = summarize_headways((PLATFORM,), ())
    assert len(summaries) == 3
    assert all(
        b["departure_count"] == 0 and b["median_s"] is None
        for s in summaries
        for b in s["bands"]
    )
