# AI contribution: 50% or more AI-generated
"""Prediction cloning retains values, concrete subclasses and random draws.

The fixed-schema constructor and dataclass replacement must produce the same
estimates. A subclass forces the original replacement path and adds metadata
that a careless fast copy could silently discard. Checking the next random
value also detects skipped or extra draws after prediction construction.
"""

from dataclasses import dataclass, replace

import numpy as np
import pytest

from simulator.control.interface import TrainState
from simulator.control.prediction_error import (
    PredictionErrorModel,
    PredictionErrorSettings,
)
from tests.simulator.control.test_prediction_error import snapshot


@dataclass(frozen=True, slots=True)
class AnnotatedTrain(TrainState):
    """An extended state must keep its extra immutable metadata."""

    annotation: str = "retained"


@pytest.mark.parametrize("seed", [0, 7, 42])
def test_prediction_clone_preserves_draw_order_and_subclass(seed):
    """Compare the standard path with dataclass replacement fallback.

    The fixture has a future arrival and a train with no next stop, so both
    draw-count branches are exercised with the same incoming transfer group.
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
    plain_stream = np.random.default_rng(seed)
    subclass_stream = np.random.default_rng(seed)
    settings = PredictionErrorSettings()
    plain = PredictionErrorModel(settings, plain_stream).apply(truth)
    copied = PredictionErrorModel(settings, subclass_stream).apply(extended)
    assert plain.incoming_transfers == copied.incoming_transfers
    for expected, actual in zip(plain.trains, copied.trains, strict=True):
        assert actual.annotation == "retained"
        assert actual.onboard_load == expected.onboard_load
        assert actual.predicted_arrival_s == expected.predicted_arrival_s
    assert plain_stream.standard_normal() == subclass_stream.standard_normal()
