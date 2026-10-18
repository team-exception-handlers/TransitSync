"""Seed management and stream separation for reproducible simulations."""

from __future__ import annotations

import random


class StreamManager:
    """Manages independent, reproducible random

    number streams derived from a master seed.
    """

    def __init__(self, master_seed: int) -> None:
        self.master_seed = master_seed
        # Initialize a root RNG to spawn sub-seeds deterministically
        self._root_rng = random.Random(master_seed)
        self._streams: dict[str, random.Random] = {}

    def get_stream(self, name: str) -> random.Random:
        """Retrieve or create an isolated random

        stream for a given component/stream name.
        """
        if name not in self._streams:
            # Derive a unique, deterministic seed for this specific stream name
            derived_seed = self._root_rng.randint(0, 2**31 - 1)
            self._streams[name] = random.Random(derived_seed)
        return self._streams[name]

    def reset(self) -> None:
        """Reset the manager and all underlying

        streams back to their initial states.
        """
        self._root_rng = random.Random(self.master_seed)
        self._streams.clear()
