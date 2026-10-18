# AI contribution: 50% or more AI-generated
"""Unit tests for seed management and stream separation."""

import pytest

from simulator.engine.random_streams import StreamManager


def test_stream_manager_reproducibility() -> None:
    """Ensure identical master seeds produce identical streams and outputs."""
    manager_a = StreamManager(master_seed=42)
    manager_b = StreamManager(master_seed=42)

    stream_a = manager_a.get_stream("walking_times")
    stream_b = manager_b.get_stream("walking_times")

    assert stream_a.random() == stream_b.random()
    assert stream_a.randint(1, 100) == stream_b.randint(1, 100)


def test_stream_isolation_and_independence() -> None:
    """Ensure stream creation order or omissions do not
    alter other streams' sequences.
    """
    mgr_a = StreamManager(master_seed=42)
    mgr_a.get_stream("walking_times")
    val_a = mgr_a.get_stream("run_times").random()

    mgr_b = StreamManager(master_seed=42)
    val_b = mgr_b.get_stream("run_times").random()

    assert val_a == val_b, (
        "Stream generation order or omissions incorrectly altered runtimes seed!"
    )


def test_using_one_stream_leaves_others_unaffected() -> None:
    """Ensure interacting with one stream doesn't
    shift or affect other streams' sequences."""

    a = StreamManager(42)
    a.get_stream("walking_times").random()

    b = StreamManager(42)

    assert a.get_stream("run_times").random() == b.get_stream("run_times").random()


def test_invalid_stream_name_raises_error() -> None:
    """Ensure unrecognised stream names or typos raise a ValueError immediately."""
    manager = StreamManager(master_seed=42)
    with pytest.raises(ValueError, match="unknown stream"):
        manager.get_stream("walking_time")  # typo check
