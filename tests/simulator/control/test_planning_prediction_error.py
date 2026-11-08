# AI contribution: 50% or more AI-generated
"""Correlated route forecasts stay consistent and detached (#61 review)."""

from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.control.observation_builder import ObservationBuilder
from simulator.control.prediction_error import (
    PredictionErrorModel,
    PredictionErrorSettings,
)
from simulator.engine.events import DepartureDue
from simulator.engine.random_streams import StreamManager
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent
from tests.simulator.control.test_prediction_error import FixedDraws


def route_snapshot():
    """Eight future stops, ten seconds apart, before any train has arrived."""
    train = Train(
        "A",
        800,
        tuple(
            ScheduledStop(f"S{i}", f"P{i}", 100 + 10 * i, 105 + 10 * i)
            for i in range(8)
        ),
    )
    decision = DepartureDue(
        time_s=0, train_id="A", station_id="S0", platform_id="P0", scheduled_s=105
    )
    return ObservationBuilder().build(decision, TrainComponent([train]), planning=True)


def test_next_stop_and_future_visit_reuse_one_error_draw():
    truth = route_snapshot()
    # Load = 0 sigma draw; arrival z = 0.5. No per-stop draws are available.
    draws = FixedDraws(0, 0.5)
    seen = PredictionErrorModel(PredictionErrorSettings(), draws).apply(truth)
    first, last = seen.future_visits[0], seen.future_visits[-1]
    assert seen.trains[0].predicted_arrival_s == first.arrival_s
    # 60 ln(100/60 + 1.4) * 0.5 = 33.6177 s; later sigma is larger.
    assert first.arrival_s == pytest.approx(133.6177, abs=1e-4)
    assert last.arrival_s - 170 > first.arrival_s - 100
    assert draws.values == []
    assert truth.future_visits[0].arrival_s == 100


@given(z=st.floats(min_value=-100, max_value=100, allow_nan=False))
def test_route_forecasts_remain_chronological_for_extreme_errors(z):
    truth = route_snapshot()
    # Supply enough draws for the old per-visit implementation too, so this
    # regression detects impossible times rather than an exhausted test stream.
    draws = FixedDraws(0, z, *([z] * 8))
    seen = PredictionErrorModel(PredictionErrorSettings(), draws).apply(truth)
    assert seen.trains[0].predicted_arrival_s == seen.future_visits[0].arrival_s
    previous = truth.time_s
    for original, estimated in zip(
        truth.future_visits, seen.future_visits, strict=True
    ):
        assert estimated.arrival_s >= previous
        assert estimated.departure_s - estimated.arrival_s == pytest.approx(
            5, abs=1e-10
        )
        assert estimated.key == original.key
        previous = estimated.departure_s


def test_seeded_next_stop_forecast_matches_route_forecast():
    truth = route_snapshot()
    model = PredictionErrorModel(
        PredictionErrorSettings(), StreamManager(42).get_stream("prediction_errors")
    )
    seen = model.apply(truth)
    assert seen.trains[0].predicted_arrival_s == seen.future_visits[0].arrival_s


def test_each_apply_uses_fresh_train_errors():
    truth = route_snapshot()
    draws = FixedDraws(0, 0.5, 0, 1)
    model = PredictionErrorModel(PredictionErrorSettings(), draws)
    first = model.apply(truth)
    second = model.apply(truth)
    assert second.future_visits[0].arrival_s > first.future_visits[0].arrival_s
    assert draws.values == []


def test_trains_have_independent_arrival_errors():
    truth = route_snapshot()
    other = replace(truth.trains[0], train_id="B")
    other_visit = replace(truth.future_visits[0], train_id="B")
    truth = replace(
        truth,
        trains=(*truth.trains, other),
        future_visits=(*truth.future_visits, other_visit),
    )
    draws = FixedDraws(0, 0.5, 0, -0.5)
    seen = PredictionErrorModel(PredictionErrorSettings(), draws).apply(truth)
    assert seen.future_visits[0].arrival_s > 100
    assert seen.future_visits[-1].arrival_s < 100
    assert seen.trains[1].predicted_arrival_s == seen.future_visits[-1].arrival_s
    assert draws.values == []


def test_future_only_train_draw_is_reused():
    truth = route_snapshot()
    # At a turnaround the next-stop view can be empty while returns remain.
    train = replace(truth.trains[0], next_platform_id=None, predicted_arrival_s=None)
    truth = replace(truth, trains=(train,))
    draws = FixedDraws(0, 0.5)
    seen = PredictionErrorModel(PredictionErrorSettings(), draws).apply(truth)
    assert seen.future_visits[0].arrival_s == pytest.approx(133.6177, abs=1e-4)
    assert draws.values == []


def test_observed_arrival_and_known_platform_bound_are_preserved():
    truth = route_snapshot()
    observed = replace(truth.future_visits[0], arrived=True)
    following = replace(truth.future_visits[1], earliest_arrival_s=109)
    truth = replace(truth, time_s=102, future_visits=(observed, following))
    seen = PredictionErrorModel(PredictionErrorSettings(), FixedDraws(0, -100)).apply(
        truth
    )
    assert seen.future_visits[0] == observed
    assert seen.future_visits[1].arrival_s == 109
    assert seen.future_visits[1].departure_s == 114


def test_planning_perfect_information_preserves_snapshot_and_draw_count():
    truth = route_snapshot()
    streams = [StreamManager(42).get_stream("prediction_errors") for _ in range(2)]
    perfect = PredictionErrorModel(PredictionErrorSettings(0, 0, 0), streams[0])
    noisy = PredictionErrorModel(PredictionErrorSettings(), streams[1])
    assert perfect.apply(truth) == truth
    noisy.apply(truth)
    assert streams[0].random() == streams[1].random()
