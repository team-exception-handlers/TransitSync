# AI contribution: 50% or more AI-generated
"""Unit tests for passenger walking time sampling."""

from __future__ import annotations

import math

import numpy as np
import pytest

from simulator.engine.random_streams import StreamManager
from simulator.engine.walking_sampler import WalkingTimeSampler


def test_walking_sampler_reproducibility():
    """Verify that identical seeds produce identical walking samples."""
    sm1 = StreamManager(master_seed=123)
    sm2 = StreamManager(master_seed=123)

    sampler1 = WalkingTimeSampler(sm1)
    sampler2 = WalkingTimeSampler(sm2)

    samples1 = sampler1.sample(size=10, mean=100.0, min_time=20.0)
    samples2 = sampler2.sample(size=10, mean=100.0, min_time=20.0)

    np.testing.assert_array_equal(samples1, samples2)


def test_walking_sampler_respects_min_time():
    """Verify that all sampled walking times strictly equal or exceed min_time."""
    sm = StreamManager(master_seed=42)
    sampler = WalkingTimeSampler(sm)

    min_time = 45.0
    samples = sampler.sample(size=1000, mean=120.0, min_time=min_time)

    assert np.all(samples >= min_time)


def test_walking_sampler_uses_default_mean():
    """Check that the sample average approximates the default mean."""
    sm = StreamManager(master_seed=42)
    sampler = WalkingTimeSampler(sm, default_mean=100.0)
    samples = sampler.sample(size=50_000, min_time=20.0)
    assert abs(float(np.mean(samples)) - 100.0) < 2.0


def test_default_mean_adjusts_when_min_time_exceeds_default():
    """Ensure target mean scales up safely if min_time exceeds default_mean."""
    sm = StreamManager(master_seed=42)
    sampler = WalkingTimeSampler(sm, default_mean=100.0)
    samples = sampler.sample(size=1000, min_time=150.0)
    assert np.all(samples >= 150.0)
    assert abs(float(np.mean(samples)) - 151.0) < 5.0


def test_mean_must_exceed_min_time():
    """Ensure that mean <= min_time correctly raises a ValueError."""
    sm = StreamManager(master_seed=42)
    sampler = WalkingTimeSampler(sm)
    with pytest.raises(ValueError, match="mean"):
        sampler.sample(mean=30.0, min_time=30.0)


def test_invalid_default_mean_is_rejected():
    sm = StreamManager(master_seed=42)
    for bad_mean in (0, -10, math.nan, math.inf, -math.inf, True, "300"):
        with pytest.raises(ValueError, match="default_mean"):
            WalkingTimeSampler(sm, default_mean=bad_mean)


def test_invalid_mean_is_rejected():
    sm = StreamManager(master_seed=42)
    sampler = WalkingTimeSampler(sm)

    for bad_mean in (20, 30, 0, -5, math.nan, math.inf, -math.inf, True, "100"):
        with pytest.raises(ValueError, match="mean"):
            sampler.sample(mean=bad_mean, min_time=30.0)


def test_invalid_min_time_is_rejected():
    sm = StreamManager(master_seed=42)
    sampler = WalkingTimeSampler(sm)

    for bad_min in (-1, math.nan, math.inf, -math.inf, True, "30"):
        with pytest.raises(ValueError, match="min_time"):
            sampler.sample(min_time=bad_min)
