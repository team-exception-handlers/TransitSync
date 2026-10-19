# AI contribution: 50% or more AI-generated
"""Unit tests for passenger walking time sampling."""

from __future__ import annotations

import numpy as np

from simulator.engine.random_streams import StreamManager
from simulator.engine.walking_sampler import WalkingTimeSampler


def test_walking_sampler_reproducibility() -> None:
    """Ensure identical master seeds produce identical walking time samples."""
    manager_a = StreamManager(master_seed=42)
    manager_b = StreamManager(master_seed=42)

    sampler_a = WalkingTimeSampler(manager_a)
    sampler_b = WalkingTimeSampler(manager_b)

    samples_a = sampler_a.sample(size=5)
    samples_b = sampler_b.sample(size=5)

    np.testing.assert_array_equal(samples_a, samples_b)


def test_walking_sampler_respects_min_time() -> None:
    """Ensure all sampled walking times respect the minimum threshold."""
    manager = StreamManager(master_seed=42)
    sampler = WalkingTimeSampler(manager)

    samples = sampler.sample(size=100, min_time=45.0)
    assert np.all(samples >= 45.0)
