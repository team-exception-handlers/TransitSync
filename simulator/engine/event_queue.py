# AI contribution: 50% or more AI-generated
"""Event queue and simulation clock.

Implements US-1.1 (Deterministic event engine), Task 1.1.2 (#8). Every other
component schedules its work through ``Scheduler.schedule`` and is called back
when the clock reaches it.

Ordering: events are processed by time, then by ``EVENT_PRIORITY`` (the tie
order documented in ``simulator.engine.events``), then by the order in which
they were scheduled. The insertion counter makes the order total, so two runs
that schedule the same events in the same order always process them in the
same order, and event objects are never compared with each other.

Clock: the clock starts at 0 and jumps straight to the time of the next event.
It never moves in fixed steps and never goes backwards. Times are in seconds.
"""

import heapq
import logging
import math
from collections.abc import Callable

from simulator.engine.events import (
    EVENT_PRIORITY,
    SCHEDULE_AT_CURRENT_TIME,
    Event,
)

log = logging.getLogger(__name__)

# Called once per processed event. A handler may schedule further events.
EventHandler = Callable[[Event], None]

# Heap entry: (time_s, tie priority, insertion counter, event)
_Entry = tuple[float, int, int, Event]


class SchedulingError(ValueError):
    """An event was scheduled in a way that would break the processing order."""


class EmptyQueueError(LookupError):
    """The next event was requested from an empty queue."""


def _order_key(event: Event) -> tuple[float, int]:
    """Time and tie priority, the part of the order that callers control."""
    return event.time_s, EVENT_PRIORITY[event.event_type]


class EventQueue:
    """Priority queue of events ordered by time, tie priority, then insertion."""

    def __init__(self) -> None:
        self._heap: list[_Entry] = []
        self._inserted = 0

    def __len__(self) -> int:
        return len(self._heap)

    def push(self, event: Event) -> None:
        """Add an event to the queue."""
        time_s, priority = _order_key(event)
        heapq.heappush(self._heap, (time_s, priority, self._inserted, event))
        self._inserted += 1

    def pop(self) -> Event:
        """Remove and return the next event.

        Raises:
            EmptyQueueError: the queue has no events.
        """
        if not self._heap:
            raise EmptyQueueError("cannot pop from an empty event queue")
        return heapq.heappop(self._heap)[-1]

    def peek_time(self) -> float | None:
        """Time of the next event in seconds, or None if the queue is empty."""
        return self._heap[0][0] if self._heap else None


class Scheduler:
    """Simulation clock plus event queue.

    This is the scheduling interface the rest of the simulator uses.
    """

    def __init__(self) -> None:
        self._queue = EventQueue()
        self._now = 0.0
        # Order key of the last processed event. Nothing may be scheduled
        # before it, or the documented processing order would be broken.
        self._last_key: tuple[float, int] | None = None

    @property
    def now(self) -> float:
        """Current simulation time in seconds."""
        return self._now

    @property
    def pending(self) -> int:
        """Number of events still waiting in the queue."""
        return len(self._queue)

    def schedule(self, event: Event) -> None:
        """Schedule an event to be processed when the clock reaches it.

        Event times are already checked to be finite and >= 0 by the event
        schema, so only the position relative to the clock is checked here.

        Raises:
            SchedulingError: the event is earlier than the current time, is
                at the current time but would come before the event that was
                just processed in the tie order, or is a type in
                ``SCHEDULE_AT_CURRENT_TIME`` scheduled for a later time.
        """
        if event.time_s < self._now:
            raise SchedulingError(
                f"cannot schedule {event.event_type.value} at {event.time_s} s, "
                f"the clock is already at {self._now} s"
            )
        if event.event_type in SCHEDULE_AT_CURRENT_TIME and event.time_s != self._now:
            raise SchedulingError(
                f"cannot schedule {event.event_type.value} at {event.time_s} s: "
                f"it must be created when it happens, at the current time "
                f"({self._now} s), so its counts are final"
            )
        if self._last_key is not None and _order_key(event) < self._last_key:
            raise SchedulingError(
                f"cannot schedule {event.event_type.value} at {event.time_s} s: "
                "an event later in the tie order has already been processed "
                "at this time"
            )
        self._queue.push(event)

    def step(self) -> Event:
        """Advance the clock to the next event and return it.

        Raises:
            EmptyQueueError: no events are left.
        """
        event = self._queue.pop()
        self._now = event.time_s
        self._last_key = _order_key(event)
        return event

    def run_until(self, end_s: float, handler: EventHandler) -> int:
        """Process events in order until none are left at or before ``end_s``.

        An event at exactly ``end_s`` is processed. Events after ``end_s``
        stay in the queue. The clock stays at the last processed event.

        Args:
            end_s: end of the simulated period, in seconds.
            handler: called with each event as it is processed.

        Returns:
            The number of events processed.

        Raises:
            SchedulingError: ``end_s`` is not finite or is before the clock.
        """
        if not math.isfinite(end_s) or end_s < self._now:
            raise SchedulingError(
                f"end_s must be finite and >= the clock ({self._now} s), got {end_s}"
            )
        log.debug("running from %s s to %s s", self._now, end_s)
        processed = 0
        while (next_time := self._queue.peek_time()) is not None and (
            next_time <= end_s
        ):
            handler(self.step())
            processed += 1
        log.debug("processed %d events, clock at %s s", processed, self._now)
        return processed
