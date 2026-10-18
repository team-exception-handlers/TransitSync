# AI contribution: 50% or more AI-generated
"""Event log writer and run summary.

Part of US-1.1 (Deterministic event engine), Task 1.1.6 (#99). The event log
is the full output of a run: the same scenario and master seed must produce a
byte-identical log, so the encoding here avoids anything that can vary
between runs or machines (key order, float formatting, line endings, wall
clock time, file paths).
"""

import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from types import TracebackType
from typing import IO, Any, Self

from simulator.engine.events import EVENT_CLASSES, Event, EventType

EVENTS_FILE = "events.jsonl"
SUMMARY_FILE = "summary.json"
# Summary fields evolve independently from the event-record schema.
SUMMARY_SCHEMA_VERSION = 3

# Skip passenger records for sweep runs, deriving their types from the schema.
PASSENGER_EVENT_TYPES: frozenset[EventType] = frozenset(
    cls.event_type
    for cls in EVENT_CLASSES.values()
    if "passenger_id" in {event_field.name for event_field in fields(cls)}
)


def partial_path(path: Path) -> Path:
    """Where a file is written before it is complete: ``<name>.partial``."""
    return path.with_name(path.name + ".partial")


def encode_record(event: Event) -> str:
    """One event as a single compact JSON line (without the newline).

    Key order comes from ``Event.to_record``, which is fixed by the schema.
    """
    return json.dumps(event.to_record(), separators=(",", ":"), allow_nan=False)


class EventLogWriter:
    """Writes events to a JSON Lines file as they are processed.

    The log is written to ``<name>.partial`` and only renamed to its final
    name when the run finishes, so a failed run never leaves behind a log
    that looks complete.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._partial = partial_path(path)
        self._file: IO[str] | None = None

    def __enter__(self) -> Self:
        # newline="\n" keeps the bytes identical on Windows and Linux
        self._file = self._partial.open("w", encoding="utf-8", newline="\n")
        return self

    def write(self, event: Event) -> None:
        """Append one event to the log."""
        if self._file is None:
            raise RuntimeError("EventLogWriter.write called outside its context")
        self._file.write(encode_record(event) + "\n")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
        if exc_type is None:
            self._partial.replace(self._path)


@dataclass
class RunSummary:
    """Counts collected while a run is processed.

    Attributes:
        master_seed: seed every random substream of the run is derived from.
        duration_s: length of the simulated period, in seconds.
        events_processed: events handled before the end of the period.
        events_pending: events still scheduled after the end of the period.
        end_time_s: clock time of the last processed event, in seconds.
        events_by_type: processed events per event type, every type listed.
        skipped_event_types: event types omitted from the event log.
    """

    master_seed: int
    duration_s: float
    events_processed: int = 0
    events_pending: int = 0
    end_time_s: float = 0.0
    events_by_type: dict[str, int] = field(
        default_factory=lambda: {event_type.value: 0 for event_type in EventType}
    )
    skipped_event_types: frozenset[EventType] = frozenset()

    def record(self, event: Event) -> None:
        """Count one processed event."""
        self.events_processed += 1
        self.events_by_type[event.event_type.value] += 1
        self.end_time_s = event.time_s

    def to_dict(self) -> dict[str, Any]:
        """Summary as a dict with a fixed key order, ready to write."""
        return {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "master_seed": self.master_seed,
            "duration_s": self.duration_s,
            "events_processed": self.events_processed,
            "events_pending": self.events_pending,
            "end_time_s": self.end_time_s,
            "events_by_type": dict(self.events_by_type),
            "skipped_event_types": sorted(
                event_type.value for event_type in self.skipped_event_types
            ),
        }


def write_summary(summary: RunSummary, path: Path) -> None:
    """Write the run summary as indented JSON."""
    text = json.dumps(summary.to_dict(), indent=2, allow_nan=False) + "\n"
    with path.open("w", encoding="utf-8", newline="\n") as file:
        file.write(text)
