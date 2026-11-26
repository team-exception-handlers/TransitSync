# AI contribution: 50% or more AI-generated
"""Warm-up compiles exactly the kernel version a real run uses.

Numba compiles one version per argument signature. If warm-up passed different
arrays from a real run, the first user request would still pay for
compilation. The test warms, records the compiled signatures, runs a real
estimate, and checks nothing was added.
"""

from dataclasses import replace
from functools import partial

from simulator.control.compiled_prediction import train_values
from simulator.control.compiled_prediction import warmup as warmup_prediction
from simulator.control.prediction_error import (
    PredictionErrorModel,
    PredictionErrorSettings,
)
from simulator.engine.random_streams import StreamManager
from tests.simulator.control.test_prediction_error import snapshot


def test_prediction_batch_after_warmup_adds_no_signature():
    """A real 64-train estimate uses only the kernel version warm-up built."""
    warmup_prediction()
    before = list(train_values.signatures)
    original = snapshot()
    truth = replace(
        original,
        trains=tuple(
            replace(original.trains[i % 2], train_id=str(i)) for i in range(64)
        ),
    )
    draw = partial(StreamManager(42).keyed_normal, "prediction_errors")
    PredictionErrorModel(PredictionErrorSettings(), draw).apply(truth)
    assert list(train_values.signatures) == before
