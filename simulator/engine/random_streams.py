# AI contribution: 50% or more AI-generated
"""Seed management and stream separation for reproducible simulations."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from statistics import NormalDist

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

_STANDARD_NORMAL = NormalDist()
# The top 53 bits of a digest fill a float's mantissa, so u is exact
_MANTISSA_BITS = 53
_DIGEST_BYTES = 16


def _key_digest(*key: object) -> int:
    """128-bit number fixed by ``key`` alone, the same in every process.

    Numbers are read as floats, so 130 and 130.0 match. repr quotes strings,
    so ("A1", "B") and ("A", "1B") never collide. hash() would change with
    PYTHONHASHSEED; hashlib never does (#191).
    """
    parts = tuple(part if isinstance(part, str) else float(part) for part in key)
    digest = hashlib.blake2b(repr(parts).encode(), digest_size=_DIGEST_BYTES)
    return int.from_bytes(digest.digest(), "little")


def _key_parts(key: tuple[object, ...]) -> tuple[str | float, ...]:
    """Keep strings and read every other part as a float, as the digest needs."""
    return tuple(part if isinstance(part, str) else float(part) for part in key)


def _prefixed_normal(prefix: tuple[object, ...]) -> Callable[..., float]:
    """Return ``draw(*rest)``, equal bit for bit to digesting ``(*prefix, *rest)``.

    repr of a tuple with two or more parts is "(" + parts joined by ", " + ")".
    The prefix always holds the seed and the stream index, so the hash of its
    opening text can be computed once and copied for every later key. That
    skips most of the hashing and repr work each draw would otherwise repeat
    (#412). The draws themselves are unchanged.

    ``draw.bind(*more)`` returns the same kind of function with ``more`` added
    to the prefix, so a caller drawing one value kind for many trains hashes
    that kind once too.
    """
    opening = "(" + ", ".join(map(repr, _key_parts(prefix)))
    copy = hashlib.blake2b(opening.encode(), digest_size=_DIGEST_BYTES).copy
    shift = 8 * _DIGEST_BYTES - _MANTISSA_BITS
    inv_cdf = _STANDARD_NORMAL.inv_cdf

    def draw(*rest: str | float) -> float:
        hasher = copy()
        if len(rest) == 1 and type(rest[0]) is str:
            # The usual case, one train or group ID, skips the general join
            hasher.update(f", {rest[0]!r})".encode())
        else:
            tail = "".join(", " + repr(part) for part in _key_parts(rest))
            hasher.update((tail + ")").encode())
        top = int.from_bytes(hasher.digest(), "little") >> shift
        # Same arithmetic as keyed_normal, so the draws are identical
        return inv_cdf((top + 0.5) / 2**_MANTISSA_BITS)

    draw.bind = lambda *more: _prefixed_normal((*prefix, *more))
    return draw


class StreamManager:
    """Manages independent, reproducible NumPy random generators
    derived from a master seed."""

    def __init__(self, master_seed: int) -> None:
        self.master_seed = master_seed
        # Digests of the keys this manager belongs to; empty for a whole run
        self._key: tuple[int, ...] = ()
        self._streams: dict[str, np.random.Generator] = {}

    def get_stream(self, name: str) -> np.random.Generator:
        """Retrieve or create an isolated NumPy random generator
        for a given stream name.

        Uses numpy.random.SeedSequence with a spawn key index so that request
        order, consumption count, or stream omissions never affect other streams.
        """
        if name not in self._streams:
            index = _stream_index(name)
            seq = np.random.SeedSequence(
                self.master_seed, spawn_key=(index, *self._key)
            )
            self._streams[name] = np.random.default_rng(seq)
        return self._streams[name]

    def keyed(self, *key: str | float) -> StreamManager:
        """Streams that belong to one thing, such as a feeder train arrival.

        Paired runs with the same seed give the same thing the same draws, even
        when a hold changes how many other things drew before it (section 9).
        No key returns this manager.
        """
        if not key:
            return self
        child = StreamManager(self.master_seed)
        child._key = (*self._key, _key_digest(*key))
        return child

    def keyed_normal(self, name: str, *key: str | float) -> float:
        """One standard normal draw fixed by the seed, ``name`` and ``key`` alone.

        e = Phi^-1(u) with u from a hash, which is about 5 times faster than a
        SeedSequence or Philox generator per draw (#191).
        """
        digest = _key_digest(self.master_seed, *self._key, _stream_index(name), *key)
        top = digest >> (8 * _DIGEST_BYTES - _MANTISSA_BITS)
        # Adding 0.5 keeps u strictly between 0 and 1, where Phi^-1 is finite
        return _STANDARD_NORMAL.inv_cdf((top + 0.5) / 2**_MANTISSA_BITS)

    def keyed_normal_from(
        self, name: str, *prefix: str | float
    ) -> Callable[..., float]:
        """Return ``draw(*rest)`` equal to ``keyed_normal(name, *prefix, *rest)``.

        Use it when many draws share the start of their key, such as every
        train in one decision. It gives the same numbers, about 3 times faster.
        """
        return _prefixed_normal(
            (self.master_seed, *self._key, _stream_index(name), *prefix)
        )

    def reset(self) -> None:
        """Reset the manager and all underlying streams back to their initial states."""
        self._streams.clear()


def _stream_index(name: str) -> int:
    if name not in STREAM_NAMES:
        raise ValueError(f"unknown stream {name!r}")
    return STREAM_NAMES.index(name)
