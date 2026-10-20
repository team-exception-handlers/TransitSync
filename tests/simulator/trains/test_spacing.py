# AI contribution: 50% or more AI-generated
"""Requested headway variance and deterministic integration for #28."""

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.engine.event_queue import Scheduler
from simulator.engine.events import TrainDeparture
from simulator.engine.random_streams import StreamManager
from simulator.trains.spacing import perturb_dispatch_times
from simulator.trains.suspension import LineSuspension
from simulator.trains.train import ScheduledStop
from simulator.trains.train_component import TrainComponent
from simulator.trains.train_generator import (
    generate_from_headway,
    generate_from_schedule,
)


def stream(seed=42):
    return StreamManager(seed).get_stream("disruptions")


def test_zero_level_keeps_timetable_and_consumes_no_random_draws():
    rng = stream()
    assert perturb_dispatch_times([100, 400, 700], 0, rng) == [100, 400, 700]
    np.testing.assert_array_equal(rng.random(10), stream().random(10))


@pytest.mark.parametrize("level", [0.1, 0.3, 0.7, 1.0])
def test_requested_headways_have_configured_mean_and_variance(level):
    # Fixed seed and 50,000 intervals: wide tolerances avoid a fragile sample test.
    nominal = np.arange(50001, dtype=float) * 300
    headways = np.diff(perturb_dispatch_times(nominal, level, stream()))
    assert np.mean(headways) == pytest.approx(300, rel=0.025)
    assert np.var(headways) == pytest.approx((300 * level) ** 2, rel=0.08)
    assert np.all(headways > 0)


def test_same_seed_repeats_spacing_and_other_streams_are_isolated():
    times = [0, 100, 300, 600]
    manager = StreamManager(42)
    manager.get_stream("walking_times").random(1000)
    assert perturb_dispatch_times(
        times, 0.5, manager.get_stream("disruptions")
    ) == perturb_dispatch_times(times, 0.5, stream())
    assert perturb_dispatch_times(times, 0.5, stream()) != perturb_dispatch_times(
        times, 0.5, stream(43)
    )


@pytest.mark.parametrize("times", [[], [10]])
def test_empty_and_single_dispatch_have_no_headway_to_perturb(times):
    assert perturb_dispatch_times(times, 0.3, stream()) == times


@pytest.mark.parametrize("level", [-1, float("nan"), float("inf"), True, "0.5"])
def test_invalid_level_is_rejected(level):
    with pytest.raises(ValueError, match="Irregularity"):
        perturb_dispatch_times([0, 100], level, stream())


@pytest.mark.parametrize("times", [[10, 10], [10, 0], [-1, 10], [0, float("nan")]])
def test_invalid_dispatch_times_are_rejected(times):
    with pytest.raises(ValueError, match="times"):
        perturb_dispatch_times(times, 0.2, stream())


def test_nonzero_irregularity_requires_explicit_seeded_stream():
    with pytest.raises(ValueError, match="seeded"):
        perturb_dispatch_times([0, 100], 0.2)


def test_both_generators_apply_irregularity_and_preserve_route_durations():
    route = (ScheduledStop("A", "P", 0, 0), ScheduledStop("B", "Q", 100, 120))
    scheduled = generate_from_schedule(
        [0, 300, 600], route, 10, "green", irregularity_level=0.3, rng=stream()
    )
    headway = generate_from_headway(
        0, 600, 300, route, 10, "green", irregularity_level=0.3, rng=stream()
    )
    assert scheduled == headway
    assert [t.schedule[0].departure_s for t in scheduled] != [0, 300, 600]
    assert all(t.line_id == "green" for t in scheduled)
    assert all(
        t.schedule[1].arrival_s - t.schedule[0].departure_s == pytest.approx(100)
        for t in scheduled
    )


@given(level=st.floats(min_value=0, max_value=2, allow_nan=False))
def test_perturbed_service_still_obeys_operational_separation(level):
    trains = generate_from_headway(
        0,
        900,
        100,
        (ScheduledStop("A", "P", 0, 0),),
        10,
        "green",
        irregularity_level=level,
        rng=stream(),
    )
    trains[0].current_delay = 180
    component = TrainComponent(
        trains, minimum_gap_s=90, suspensions=[LineSuspension("green", 100, 400)]
    )
    scheduler = Scheduler()
    component.start(scheduler)
    departures = []

    def handle(event):
        component.handle(event, scheduler)
        if isinstance(event, TrainDeparture):
            departures.append(event)

    scheduler.run_until(100000, handle)
    assert len(departures) == len(trains)
    assert [e.train_id for e in departures] == [t.id for t in trains]
    assert all(
        b.time_s - a.time_s >= 90
        for a, b in zip(departures, departures[1:], strict=False)
    )
    assert all(not 100 <= e.time_s < 400 for e in departures)
