# AI contribution: 50% or more AI-generated
"""Prediction cloning retains values, concrete subclasses and keyed draws.

The fixed-schema constructor and dataclass replacement must produce the same
estimates. A subclass forces the original replacement path and adds metadata
that a careless fast copy could silently discard. Each error is keyed by what
it predicts (#192), so the fast path (prefix-bound draws and compiled
arithmetic) must give exactly the values of the plain one-train-at-a-time path.
"""

from dataclasses import dataclass, fields, replace
from functools import partial

import pytest

from simulator.control.interface import TrainState
from simulator.control.planning import FutureVisit
from simulator.control.prediction_error import (
    BoundDraw,
    PredictionErrorModel,
    PredictionErrorSettings,
    _decision_draw,
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
    """A float subclass the compiled path refuses, forcing scalar arithmetic."""


def scalar(seed):
    """Same keyed numbers, but neither prefix-bound nor batched."""
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
def test_batched_keyed_trains_match_scalar_values(seed, size, kappa):
    """Mixed next-stop branches give the scalar path's exact values.

    Sizes below and above the 32-train batching threshold, the real hourly
    population and perfect information (kappa 0) are all covered. Repeating
    the snapshot checks that the reused input rows change nothing.
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
    """Only the run's keyed source is batched; any other callable keeps main's
    contract of one call per value, load before arrival, train by train.

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


def test_fast_copies_follow_the_dataclass_field_order():
    """The positional copies break loudly if a field is added or reordered.

    A new field with a default would otherwise be reset silently on copy.
    """
    assert [f.name for f in fields(TrainState)] == [
        "train_id",
        "line_id",
        "next_platform_id",
        "predicted_arrival_s",
        "scheduled_departure_s",
        "delay_s",
        "onboard_load",
        "capacity",
    ]
    assert [f.name for f in fields(FutureVisit)] == [
        "train_id",
        "trip_index",
        "stop_index",
        "station_id",
        "platform_id",
        "arrival_s",
        "departure_s",
        "scheduled_arrival_s",
        "scheduled_departure_s",
        "can_hold",
        "skips_departure",
        "recovery_s",
        "arrived",
        "earliest_arrival_s",
    ]


def test_the_run_draw_takes_the_prefix_fast_path():
    """The form the API builds is bound once; any other callable is wrapped.

    If the API wrapped its draw differently the numbers would stay right but
    the speed-up would vanish, so this checks the path, not the values.
    """
    decision = ("A", "P1", 130.0)
    bound = _decision_draw(keyed(7), decision)
    assert not isinstance(bound, partial)
    assert isinstance(bound, BoundDraw)
    custom = _decision_draw(ExactFloat, decision)
    assert isinstance(custom, partial)
    assert not isinstance(custom, BoundDraw)


@pytest.mark.parametrize(("size", "calls"), [(31, 0), (32, 1), (1679, 1)])
def test_the_run_draw_uses_the_compiled_kernel_from_32_trains(monkeypatch, size, calls):
    """Below 32 trains a compiled call costs more than it saves.

    Checks the path, not the values: the batched test above covers those.
    """
    import simulator.control.compiled_prediction as compiled

    original_kernel = compiled.train_values
    used = []

    def counting(*args):
        used.append(len(args[0]))
        return original_kernel(*args)

    monkeypatch.setattr(compiled, "train_values", counting)
    original = snapshot()
    truth = replace(
        original,
        trains=tuple(
            replace(original.trains[i % 2], train_id=str(i)) for i in range(size)
        ),
    )
    PredictionErrorModel(PredictionErrorSettings(), keyed(7)).apply(truth)
    assert used == [size] * calls


def test_large_multipliers_stay_on_python_arithmetic(monkeypatch):
    """Kappa above 10,000 could overflow int64 rounding, so it is not batched."""
    import simulator.control.compiled_prediction as compiled

    monkeypatch.setattr(
        compiled, "train_values", lambda *args: pytest.fail("kernel was used")
    )
    original = snapshot()
    truth = replace(
        original,
        trains=tuple(
            replace(original.trains[i % 2], train_id=str(i)) for i in range(64)
        ),
    )
    settings = PredictionErrorSettings(1e5, 1.0, 1.0)
    fast = PredictionErrorModel(settings, keyed(7)).apply(truth)
    slow = PredictionErrorModel(settings, scalar(7)).apply(truth)
    assert repr(fast) == repr(slow)
