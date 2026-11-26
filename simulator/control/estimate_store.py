# AI contribution: 50% or more AI-generated
"""Bound full-day estimate memory while retaining every original audit byte.

The complete audit spills to an owned temporary file after eight MiB. Compact
playback lines stay in memory. Public readers still receive the full records;
independent iterators use offsets so reading never changes another reader's
position. The file closes when this run's store is released, including errors.
"""

from collections.abc import Iterator
from tempfile import SpooledTemporaryFile
from threading import Lock
from weakref import finalize

from simulator.control.decision_audit import EncodedDecisionRecord


class EstimateStore:
    """An append-only, run-local collection of immutable encoded estimates."""

    def __init__(self, *, memory_limit_bytes: int = 8 * 1024**2) -> None:
        self._file = SpooledTemporaryFile(max_size=memory_limit_bytes, mode="w+b")
        self._entries: list[tuple[int, int, str | None]] = []
        # The simulator is single-threaded, but a finished run's audit can be
        # read from an API thread; the lock keeps each seek and read together
        self._lock = Lock()
        finalize(self, self._file.close)

    def append(self, record: EncodedDecisionRecord) -> None:
        """Retain full UTF-8 bytes and their smaller playback projection."""
        data = record.line.encode("utf-8")
        with self._lock:
            self._file.seek(0, 2)
            offset = self._file.tell()
            self._file.write(data)
            self._entries.append((offset, len(data), record.decision_line))

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[EncodedDecisionRecord]:
        """Read complete records without retaining a second full audit tree."""
        for offset, length, compact in tuple(self._entries):
            with self._lock:
                self._file.seek(offset)
                line = self._file.read(length).decode("utf-8")
            yield EncodedDecisionRecord(line, compact)

    def playback_records(self) -> Iterator[EncodedDecisionRecord]:
        """Reuse projections after the runner has validated/written full audits."""
        for index, (_, _, compact) in enumerate(tuple(self._entries)):
            if compact is None:
                # Generic encoded records may lack a projection. Preserve their
                # full contents rather than silently omitting playback inputs.
                offset, length, _ = self._entries[index]
                with self._lock:
                    self._file.seek(offset)
                    compact = self._file.read(length).decode("utf-8")
            yield EncodedDecisionRecord(compact, compact)
