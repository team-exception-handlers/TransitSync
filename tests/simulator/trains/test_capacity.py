# AI contribution: 50% or more AI-generated
"""Whole-passenger capacity boundaries for #24, including NumPy callers.

Integral-looking floats remain invalid: accepting them would leave fractional
capacity arithmetic in the queue owner. NumPy integer scalars are valid inputs.
"""

import numpy as np
import pytest

from simulator.trains.train import ScheduledStop, Train

STOP = (ScheduledStop("A", "P", 0, 10),)


@pytest.mark.parametrize("field", ["capacity", "onboard_load"])
@pytest.mark.parametrize(
    "value", [True, np.bool_(True), 1.5, 2.0, "2", None, float("nan"), float("inf")]
)
def test_non_integer_capacity_and_load_rejected_before_boarding(field, value):
    """Reject fractional states before boarding can consume queue entries."""
    values = dict(capacity=3, onboard_load=0)
    values[field] = value
    with pytest.raises(ValueError, match=field):
        Train("t", schedule=STOP, **values)


@pytest.mark.parametrize("capacity,load", [(0, 0), (-1, 0), (3, -1), (3, 4)])
def test_invalid_capacity_ranges(capacity, load):
    """Reject zero capacity, negative counts and an initially overfull train."""
    with pytest.raises(ValueError):
        Train("t", capacity, STOP, onboard_load=load)


def test_numpy_capacity_and_movements_use_unbounded_python_arithmetic():
    """Small fixed-width operands must not wrap the load at 127."""
    train = Train("t", np.int64(200), STOP, onboard_load=np.int8(120))
    train.board(np.int8(10))
    assert train.onboard_load == 130
    assert type(train.onboard_load) is int
    assert type(train.capacity) is int
    train.alight(np.int8(10))
    assert train.onboard_load == 120


@pytest.mark.parametrize("method", ["board", "alight"])
@pytest.mark.parametrize("count", [True, np.bool_(True), 0.5, -1, 4])
def test_invalid_movement_preserves_load(method, count):
    """An invalid boarding or alighting request must not change the train."""
    train = Train("t", 4, STOP, onboard_load=2)
    move = getattr(train, method)
    with pytest.raises(ValueError):
        move(count)
    assert train.onboard_load == 2


@pytest.mark.parametrize("method,load", [("board", 0), ("alight", 2**63 - 1)])
def test_large_unsigned_movement_does_not_round_past_limit(method, load):
    """Compare integers exactly across Python/NumPy signedness boundaries."""
    train = Train("t", 2**63 - 1, STOP, onboard_load=load)
    move = getattr(train, method)
    count = np.uint64(2**63)
    with pytest.raises(ValueError):
        move(count)
    assert train.onboard_load == load
