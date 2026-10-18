# AI contribution: 50% or more AI-generated
"""Unit tests for seed management and stream separation."""

from simulator.engine.random_streams import StreamManager


def test_stream_manager_reproducibility() -> None:
    """Ensure identical master seeds produce identical streams and outputs."""
    manager_a = StreamManager(master_seed=42)
    manager_b = StreamManager(master_seed=42)

    stream_a = manager_a.get_stream("walking_times")
    stream_b = manager_b.get_stream("walking_times")

    assert stream_a.random() == stream_b.random()
    assert stream_a.randint(1, 100) == stream_b.randint(1, 100)


def test_stream_isolation() -> None:
    """Ensure different stream names do not cross-contaminate or share sequences."""
    manager = StreamManager(master_seed=123)

    walking_stream = manager.get_stream("walking")
    runtime_stream = manager.get_stream("runtimes")

    val_walk = walking_stream.random()
    val_runtime = runtime_stream.random()

    # Different streams should generate independent values
    assert val_walk != val_runtime
