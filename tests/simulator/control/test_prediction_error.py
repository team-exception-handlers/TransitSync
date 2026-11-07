# AI contribution: 50% or more AI-generated
"""Tests for the prediction error model (US-2.1, Task 2.1.3, #39)."""

import math

import numpy as np
import pytest

from simulator.control.interface import (
    IncomingTransfer,
    ObservationSnapshot,
    PlatformState,
    TrainState,
)
from simulator.control.prediction_error import (
    PredictionErrorModel,
    PredictionErrorSettings,
    arrival_sigma_s,
)
from simulator.engine.random_streams import StreamManager


class FixedDraws:
    """Generator stand-in returning the given standard normal values in order."""

    def __init__(self, *values):
        self.values = list(values)

    def standard_normal(self):
        return self.values.pop(0)


def snapshot(arrival_s=220.0, load=300, still_walking=12, group_size=15):
    # At 100 s: A is due at P2 at 220 s (horizon 120 s); B has no next stop
    trains = (
        TrainState("A", "rem", "P2", arrival_s, 230.0, 15.0, load, 780),
        TrainState("B", "rem", None, None, None, 0.0, 40, 780),
    )
    return ObservationSnapshot(
        time_s=100.0,
        train_id="A",
        station_id="S1",
        platform_id="P1",
        scheduled_departure_s=130.0,
        trains=trains,
        platforms=(PlatformState("P2", 25, 60.0),),
        incoming_transfers=(
            IncomingTransfer("g1", "P2", still_walking, 140.0, 190.0, 90.0, group_size),
        ),
    )


def prediction_stream(seed=7):
    return StreamManager(seed).get_stream("prediction_errors")


def test_sigma_grows_with_horizon():
    # 60 ln(tau_min + 1.4): 20.19 s now, 73.43 s at 2 min, 146.02 s at 10 min
    assert arrival_sigma_s(0) == pytest.approx(60 * math.log(1.4))
    assert arrival_sigma_s(120) == pytest.approx(73.4265, abs=1e-4)
    assert arrival_sigma_s(600) == pytest.approx(146.0168, abs=1e-4)


def test_past_due_horizon_uses_zero_horizon():
    assert arrival_sigma_s(-30) == arrival_sigma_s(0)


def test_error_applied_to_arrival_load_and_transfer_counts():
    # Draw order: A load, A arrival, B load, transfer group
    draws = FixedDraws(1.0, -0.5, 0.0, 2.0)
    seen = PredictionErrorModel(PredictionErrorSettings(), draws).apply(snapshot())
    a, b = seen.trains
    # 220 - 0.5 * 73.4265 = 183.2867; load 300 * 1.1 = 330
    assert a.predicted_arrival_s == pytest.approx(183.2867, abs=1e-4)
    assert a.onboard_load == 330
    assert (b.predicted_arrival_s, b.onboard_load) == (None, 40)
    # 12 * 1.2 = 14.4 -> 14 still walking; 15 * 1.2 = 18 in the group
    group = seen.incoming_transfers[0]
    assert (group.passenger_count, group.group_size) == (14, 18)
    assert draws.values == []


def test_values_without_error_are_copied_unchanged():
    truth = snapshot()
    seen = PredictionErrorModel(PredictionErrorSettings(), prediction_stream()).apply(
        truth
    )
    assert seen.platforms == truth.platforms
    assert seen.trains[0].delay_s == truth.trains[0].delay_s
    assert seen.incoming_transfers[0].last_arrival_s == 190.0


def test_each_value_has_its_own_multiplier():
    settings = PredictionErrorSettings(arrival_kappa=0, transfer_kappa=0.5)
    draws = FixedDraws(1.0, -0.5, 0.0, 2.0)
    seen = PredictionErrorModel(settings, draws).apply(snapshot())
    assert seen.trains[0].predicted_arrival_s == 220.0
    assert seen.trains[0].onboard_load == 330
    # 12 * 1.1 = 13.2 -> 13; 15 * 1.1 = 16.5 -> 16 (round half to even)
    group = seen.incoming_transfers[0]
    assert (group.passenger_count, group.group_size) == (13, 16)


def test_perfect_information_returns_true_values():
    truth = snapshot()
    settings = PredictionErrorSettings(0, 0, 0)
    seen = PredictionErrorModel(settings, prediction_stream()).apply(truth)
    assert settings.perfect_information
    assert seen == truth


def test_perfect_information_uses_the_stream_like_any_other_magnitude():
    # Same draws at every kappa, so a sweep compares the same errors scaled
    streams = [prediction_stream(), prediction_stream()]
    for settings, stream in zip(
        (PredictionErrorSettings(0, 0, 0), PredictionErrorSettings()),
        streams,
        strict=True,
    ):
        PredictionErrorModel(settings, stream).apply(snapshot())
    assert streams[0].random() == streams[1].random()


def test_counts_never_go_below_zero():
    draws = FixedDraws(-20.0, 0.0, -20.0, -20.0)
    seen = PredictionErrorModel(PredictionErrorSettings(), draws).apply(snapshot())
    assert seen.trains[0].onboard_load == 0
    group = seen.incoming_transfers[0]
    assert (group.passenger_count, group.group_size) == (0, 0)


def test_estimates_are_plain_python_values():
    seen = PredictionErrorModel(PredictionErrorSettings(), prediction_stream()).apply(
        snapshot()
    )
    assert type(seen.trains[0].predicted_arrival_s) is float
    assert type(seen.trains[0].onboard_load) is int
    assert type(seen.incoming_transfers[0].passenger_count) is int


def test_same_seed_gives_same_estimates():
    first, second = (
        PredictionErrorModel(PredictionErrorSettings(), prediction_stream()).apply(
            snapshot()
        )
        for _ in range(2)
    )
    assert first == second


@pytest.mark.parametrize(("kappa", "horizon_s"), [(1.0, 120), (2.0, 120), (1.0, 600)])
def test_error_spread_matches_kappa_times_sigma(kappa, horizon_s):
    # Blackbox: over many decisions the gap between estimate and truth has
    # spread kappa * sigma(tau), so doubling kappa doubles the gap
    model = PredictionErrorModel(
        PredictionErrorSettings(arrival_kappa=kappa), prediction_stream()
    )
    truth = snapshot(arrival_s=100.0 + horizon_s)
    errors = [
        model.apply(truth).trains[0].predicted_arrival_s
        - truth.trains[0].predicted_arrival_s
        for _ in range(4000)
    ]
    expected = kappa * arrival_sigma_s(horizon_s)
    assert np.std(errors) == pytest.approx(expected, rel=0.05)
    assert abs(np.mean(errors)) < 0.1 * expected


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"arrival_kappa": -0.1}, "arrival_kappa"),
        ({"transfer_kappa": math.nan}, "transfer_kappa"),
        ({"load_kappa": math.inf}, "load_kappa"),
        ({"arrival_kappa": True}, "arrival_kappa"),
        ({"load_kappa": "1"}, "load_kappa"),
    ],
)
def test_settings_reject_bad_multipliers(kwargs, field):
    with pytest.raises(ValueError, match=field):
        PredictionErrorSettings(**kwargs)


@pytest.mark.parametrize(
    ("kappas", "expected"),
    [((0, 0, 0), True), ((0, 0, 0.1), False), ((1, 1, 1), False)],
)
def test_only_all_zero_multipliers_are_perfect_information(kappas, expected):
    assert PredictionErrorSettings(*kappas).perfect_information is expected


def test_settings_save_as_floats():
    assert PredictionErrorSettings(1, 0.5, 0).to_dict() == {
        "arrival_kappa": 1.0,
        "transfer_kappa": 0.5,
        "load_kappa": 0.0,
    }
