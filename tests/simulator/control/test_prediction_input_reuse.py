# AI contribution: 50% or more AI-generated
"""Reused numeric inputs never freeze live values or change keyed draws.

The model keeps validated input rows for the identical frozen train object at
the same position. A fresh model with an emptied cache is the reference, so any
stale row would show up as a different estimate.
"""

from dataclasses import replace
from functools import partial

import pytest

from simulator.control.prediction_error import (
    PredictionErrorModel,
    PredictionErrorSettings,
)
from simulator.engine.random_streams import StreamManager
from tests.simulator.control.test_prediction_error import snapshot


def keyed(seed):
    """The draw the run passes: keyed normals on the prediction error stream."""
    return partial(StreamManager(seed).keyed_normal, "prediction_errors")


@pytest.mark.parametrize("seed", [0, 7, 42])
@pytest.mark.parametrize("kappa", [0, 1, 3])
def test_cached_rows_match_fresh_rows_after_live_changes(seed, kappa):
    """Changes in identity, load, arrival and None draw branches remain visible."""
    truth = snapshot()
    truth = replace(
        truth,
        trains=tuple(replace(truth.trains[i % 2], train_id=str(i)) for i in range(64)),
    )
    settings = PredictionErrorSettings(kappa, kappa, kappa)
    cached = PredictionErrorModel(settings, keyed(seed))
    fresh = PredictionErrorModel(settings, keyed(seed))
    for arrival, load in (
        (100.0, 300),
        (100.0, 300),
        (None, 350),
        (-0.0, 0),
        (0.0, 0),
        (120.25, 351),
    ):
        changed = replace(
            truth.trains[0], predicted_arrival_s=arrival, onboard_load=load
        )
        truth = replace(truth, trains=(changed, *truth.trains[1:]))
        fresh._train_rows.clear()
        assert repr(cached.apply(truth)) == repr(fresh.apply(truth))
    truth = replace(truth, trains=tuple(reversed(truth.trains)))
    fresh._train_rows.clear()
    assert repr(cached.apply(truth)) == repr(fresh.apply(truth))


def test_reused_input_population_remains_bounded():
    """A model used across changing networks cannot retain every old snapshot."""
    truth = snapshot()
    model = PredictionErrorModel(PredictionErrorSettings(), keyed(42))
    for offset in (0, 9000):
        trains = tuple(
            replace(truth.trains[0], train_id=str(i + offset)) for i in range(9000)
        )
        model.apply(replace(truth, trains=trains))
    assert len(model._train_rows) == 8192
