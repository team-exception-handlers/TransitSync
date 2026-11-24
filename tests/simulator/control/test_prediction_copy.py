# AI contribution: 50% or more AI-generated
"""Prediction cloning retains values, concrete subclasses and keyed draws.

The fixed-schema constructor and dataclass replacement must produce the same
estimates. A subclass forces the original replacement path and adds metadata
that a careless fast copy could silently discard. Each error is keyed by what
it predicts (#192), so the fast path (draws bound to each decision's key
prefix) must give exactly the values of drawing every full key separately.
"""

from dataclasses import dataclass, replace
from functools import partial

import pytest

from simulator.control.interface import TrainState
from simulator.control.prediction_error import (
    PredictionErrorModel,
    PredictionErrorSettings,
)
from simulator.engine.random_streams import StreamManager
from tests.simulator.control.test_prediction_error import snapshot


@dataclass(frozen=True, slots=True)
class AnnotatedTrain(TrainState):
    """An extended state must keep its extra immutable metadata."""

    annotation: str = "retained"


def keyed(seed):
    """The draw the run passes: keyed normals on the prediction error stream."""
    return partial(StreamManager(seed).keyed_normal, "prediction_errors")


class ExactFloat(float):
    """A float subclass, so a custom draw is told apart from the run's source."""


def scalar(seed):
    """Same keyed numbers, each drawn from its full key (not prefix-bound)."""
    draw = keyed(seed)
    return lambda *key: ExactFloat(draw(*key))


@pytest.mark.parametrize("seed", [0, 7, 42])
def test_prediction_clone_preserves_keyed_draws_and_subclass(seed):
    """Compare the standard path with dataclass replacement fallback.

    The fixture has a future arrival and a train with no next stop, so both
    draw branches are exercised with the same incoming transfer group.
    """
    truth = snapshot()
    extended = replace(
        truth,
        trains=tuple(
            AnnotatedTrain(
                train.train_id,
                train.line_id,
                train.next_platform_id,
                train.predicted_arrival_s,
                train.scheduled_departure_s,
                train.delay_s,
                train.onboard_load,
                train.capacity,
            )
            for train in truth.trains
        ),
    )
    settings = PredictionErrorSettings()
    plain = PredictionErrorModel(settings, keyed(seed)).apply(truth)
    copied = PredictionErrorModel(settings, keyed(seed)).apply(extended)
    assert plain.incoming_transfers == copied.incoming_transfers
    for expected, actual in zip(plain.trains, copied.trains, strict=True):
        assert actual.annotation == "retained"
        assert actual.onboard_load == expected.onboard_load
        assert actual.predicted_arrival_s == expected.predicted_arrival_s


@pytest.mark.parametrize("seed", [0, 7, 42])
@pytest.mark.parametrize("size", [0, 1, 64, 1679])
@pytest.mark.parametrize("kappa", [0, 1, 3])
def test_prefix_bound_trains_match_full_key_draws(seed, size, kappa):
    """Mixed next-stop branches give the full-key path's exact values.

    Empty, single, small and the real hourly population (1,679 trains) are
    covered, with perfect information (kappa 0) too. Repeating the snapshot
    checks that nothing carries over between decisions.
    """
    original = snapshot()
    trains = tuple(
        replace(original.trains[i % 2], train_id=str(i)) for i in range(size)
    )
    truth = replace(original, trains=trains)
    settings = PredictionErrorSettings(kappa, kappa, kappa)
    batched = PredictionErrorModel(settings, keyed(seed))
    plain = PredictionErrorModel(settings, scalar(seed))
    for _ in range(3):
        fast, slow = batched.apply(truth), plain.apply(truth)
        assert repr(fast) == repr(slow)
        assert all(type(t.onboard_load) is int for t in fast.trains)


@pytest.mark.parametrize("value_type", [float, ExactFloat])
def test_custom_draw_is_called_once_per_value_in_train_order(value_type):
    """A custom callable keeps main's contract: one call per value, load
    before arrival, train by train.

    A counter makes the callable stateful, so a second call or a different
    order would also change the estimates.
    """
    original = snapshot()
    truth = replace(
        original,
        trains=tuple(
            replace(original.trains[i % 2], train_id=str(i)) for i in range(64)
        ),
    )
    calls = []

    def counting(*key):
        calls.append(key)
        return value_type(len(calls) / 100)

    PredictionErrorModel(PredictionErrorSettings(), counting).apply(truth)
    decision = (truth.train_id, truth.platform_id, truth.scheduled_departure_s)
    expected = []
    for train in truth.trains:
        expected.append((*decision, "load", train.train_id))
        if train.predicted_arrival_s is not None:
            expected.append((*decision, "arrival", train.train_id))
    expected += [
        (*decision, "transfer", group.group_id) for group in truth.incoming_transfers
    ]
    assert calls == expected
