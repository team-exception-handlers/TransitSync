# AI contribution: 50% or more AI-generated
"""Unit tests for transit vehicle run time sampling."""

from __future__ import annotations

from simulator.engine.random_streams import StreamManager
from simulator.engine.runtime_sampler import RunTimeSampler


def test_runtime_sampler_reproducibility() -> None:
    """Ensure identical master seeds produce identical run time samples."""
    manager_a = StreamManager(master_seed=42)
    manager_b = StreamManager(master_seed=42)

    sampler_a = RunTimeSampler(manager_a)
    sampler_b = RunTimeSampler(manager_b)

    time_a = sampler_a.sample_runtime(scheduled_time=300.0)
    time_b = sampler_b.sample_runtime(scheduled_time=300.0)

    assert time_a == time_b


def test_runtime_sampler_zero_or_negative_schedule() -> None:
    """Ensure non-positive scheduled times immediately return zero."""
    manager = StreamManager(master_seed=42)
    sampler = RunTimeSampler(manager)

    assert sampler.sample_runtime(scheduled_time=0.0) == 0.0
    assert sampler.sample_runtime(scheduled_time=-50.0) == 0.0
