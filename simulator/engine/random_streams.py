# AI contribution: 50% or more AI-generated
"""Seed management and stream separation for reproducible simulations."""

from __future__ import annotations

import hashlib
import random

STREAM_NAMES = (
    "walking_times",
    "group_sizes",
    "run_times",
    "disruptions",
    "loads",
    "prediction_errors",
)


class StreamManager:
    """Manages independent, reproducible random

    number streams derived from a master seed.
    """

    def __init__(self, master_seed: int) -> None:
        self.master_seed = master_seed
        self._streams: dict[str, random.Random] = {}

    def get_stream(self, name: str) -> random.Random:
        """Retrieve or create an isolated random stream

        for a given component/stream name.
        """
        if name not in STREAM_NAMES:
            raise ValueError(f"unknown stream {name!r}")

        if name not in self._streams:
            key = f"{self.master_seed}:{name}".encode()
            hash_digest = hashlib.sha256(key).digest()
            derived_seed = int.from_bytes(hash_digest[:8], byteorder="big")
            self._streams[name] = random.Random(derived_seed)
        return self._streams[name]

    def reset(self) -> None:
        """Reset the manager and all underlying

        streams back to their initial states.
        """
        self._streams.clear()
