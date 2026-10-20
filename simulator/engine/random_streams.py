# AI contribution: 50% or more AI-generated
"""Seed management and stream separation for reproducible simulations."""

from __future__ import annotations

import numpy as np

# IMPORTANT: Always append new stream names to the end of this tuple.
# Never insert or reorder items, as their index is used in SeedSequence spawn keys.
STREAM_NAMES = (
    "walking_times",
    "group_sizes",
    "run_times",
    "disruptions",
    "loads",
    "prediction_errors",
    "destinations",
)


class StreamManager:
    """Manages independent, reproducible NumPy random generators
    derived from a master seed."""

    def __init__(self, master_seed: int) -> None:
        self.master_seed = master_seed
        self._streams: dict[str, np.random.Generator] = {}

    def get_stream(self, name: str) -> np.random.Generator:
        """Retrieve or create an isolated NumPy random generator
        for a given stream name.

        Uses numpy.random.SeedSequence with a spawn key index so that request
        order, consumption count, or stream omissions never affect other streams.
        """
        if name not in STREAM_NAMES:
            raise ValueError(f"unknown stream {name!r}")

        if name not in self._streams:
            index = STREAM_NAMES.index(name)
            seq = np.random.SeedSequence(self.master_seed, spawn_key=(index,))
            self._streams[name] = np.random.default_rng(seq)
        return self._streams[name]

    def reset(self) -> None:
        """Reset the manager and all underlying streams back to their initial states."""
        self._streams.clear()
