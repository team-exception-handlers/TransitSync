# AI contribution: 50% or more AI-generated
"""Simulation runner: runs one scenario from start to end and writes its output.

Implements US-1.1 (Deterministic event engine), Task 1.1.6 (#99).

The runner only wires things together, so it depends on small interfaces
rather than on concrete classes that other tasks provide:

- ``Scenario``: the validated scenario configuration (Task 1.1.5, #98)
- ``StreamFactory``: builds the random substreams from the master seed
  (Task 1.1.3, #9)
- ``ComponentFactory``: builds the network, trains and passengers
  (Task 1.1.4, #97, then US-1.2 and US-1.3)

A component follows the Architecture page: the event queue drives train logic
and passenger logic, which react to events by scheduling new ones. Every
component sees every event, in the fixed order of the component list, so the
dispatch order is deterministic. No control strategy is involved yet.

Output, written to ``output_dir``:

- ``events.jsonl``: processed events except skipped types, one JSON record per line
- ``summary.json``: counts for the run

The two files always come from the same run. A folder that already holds
either file is rejected before the run starts, and a run that fails removes
everything it wrote, so a failed rerun never leaves old and new results mixed.
"""

import logging
import math
from collections.abc import Callable, Sequence, Set
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from simulator.engine.event_log import (
    EVENTS_FILE,
    SUMMARY_FILE,
    EventLogWriter,
    RunSummary,
    partial_path,
    write_summary,
)
from simulator.engine.event_queue import Scheduler
from simulator.engine.events import Event, EventType

log = logging.getLogger(__name__)


class Scenario(Protocol):
    """The parts of a scenario the runner reads."""

    @property
    def duration_s(self) -> float:
        """Length of the simulated period, in seconds."""
        ...

    @property
    def master_seed(self) -> int:
        """Seed that every random substream of the run is derived from."""
        ...


class Component(Protocol):
    """A part of the simulation that schedules and reacts to events."""

    def start(self, scheduler: Scheduler) -> None:
        """Schedule the component's first events, before the clock starts."""
        ...

    def handle(self, event: Event, scheduler: Scheduler) -> None:
        """React to a processed event, possibly by scheduling new events."""
        ...


# The runner only passes the random streams on to the components, so their
# type is left to the stream factory (Task 1.1.3, #9)
StreamFactory = Callable[[int], object]
ComponentFactory = Callable[[Scenario, object], Sequence[Component]]


class RunError(RuntimeError):
    """A run could not be completed or its output could not be written."""


@dataclass(frozen=True)
class RunResult:
    """What a finished run produced."""

    summary: RunSummary
    events_path: Path
    summary_path: Path


def _check_scenario(scenario: Scenario) -> None:
    """Reject values the runner cannot work with before any file is created."""
    duration_s = scenario.duration_s
    if isinstance(duration_s, bool) or not isinstance(duration_s, int | float):
        raise ValueError("scenario.duration_s must be a number of seconds")
    if not math.isfinite(duration_s) or duration_s < 0:
        raise ValueError(
            f"scenario.duration_s must be finite and >= 0, got {duration_s}"
        )
    seed = scenario.master_seed
    # SeedSequence only accepts non-negative integers
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError(
            f"scenario.master_seed must be a non-negative integer, got {seed!r}"
        )


def _check_skipped_event_types(
    skip_event_types: Set[EventType] | None,
) -> frozenset[EventType]:
    """Validate and copy the log filter before components start."""
    if skip_event_types is None:
        return frozenset()
    if not isinstance(skip_event_types, Set) or any(
        not isinstance(event_type, EventType) for event_type in skip_event_types
    ):
        raise ValueError("skip_event_types must be a set of EventType values")
    return frozenset(skip_event_types)


def _check_output_dir(events_path: Path, summary_path: Path) -> None:
    """Reject a folder that already holds the output of another run."""
    existing = [path.name for path in (events_path, summary_path) if path.exists()]
    if existing:
        raise RunError(
            f"{events_path.parent} already contains run output "
            f"({', '.join(existing)}); use an empty or new folder"
        )


def _discard_output(events_path: Path, summary_path: Path) -> None:
    """Remove every file a failed run wrote, finished or partial.

    Safe because ``_check_output_dir`` made sure none of them existed before
    the run. A file that cannot be removed is logged, not raised, so the
    error that failed the run is the one the caller sees.
    """
    for path in (events_path, summary_path):
        for leftover in (path, partial_path(path)):
            try:
                leftover.unlink(missing_ok=True)
            except OSError as error:
                log.warning("could not remove %s: %s", leftover, error)


def _process_events(
    scheduler: Scheduler,
    components: Sequence[Component],
    summary: RunSummary,
    events_path: Path,
    end_s: float,
    skip_event_types: frozenset[EventType],
) -> None:
    """Process all events up to ``end_s`` seconds, logging selected types."""
    with EventLogWriter(events_path) as event_log:

        def process(event: Event) -> None:
            # Log first, so the log shows the event before anything the
            # components schedule in response to it
            if event.event_type not in skip_event_types:
                event_log.write(event)
            summary.record(event)
            for component in components:
                component.handle(event, scheduler)

        scheduler.run_until(end_s, process)
    summary.events_pending = scheduler.pending


def run_scenario(
    scenario: Scenario,
    build_streams: StreamFactory,
    build_components: ComponentFactory,
    output_dir: Path,
    *,
    skip_event_types: Set[EventType] | None = None,
) -> RunResult:
    """Run one scenario from time 0 to ``scenario.duration_s``.

    Args:
        scenario: validated scenario configuration.
        build_streams: builds the random substreams from the master seed.
        build_components: builds the components from the scenario and streams.
        output_dir: folder for the event log and summary. Created if missing.
            Must not already contain an event log or summary.
        skip_event_types: event types omitted from the log (US-1.3, #21).
            Defaults to logging everything. Use ``PASSENGER_EVENT_TYPES``
            from ``event_log`` to disable detailed passenger recording.
            All events still reach components and contribute to the summary.

    Raises:
        ValueError: the scenario duration, master seed or log filter is invalid.
        RunError: the output folder already holds run output, or the output
            could not be written. Nothing from this run is left behind.
    """
    _check_scenario(scenario)
    skipped_types = _check_skipped_event_types(skip_event_types)
    events_path = output_dir / EVENTS_FILE
    summary_path = output_dir / SUMMARY_FILE
    _check_output_dir(events_path, summary_path)
    streams = build_streams(scenario.master_seed)
    components = list(build_components(scenario, streams))
    scheduler = Scheduler()
    for component in components:
        component.start(scheduler)

    seed = scenario.master_seed
    summary = RunSummary(
        master_seed=seed,
        duration_s=float(scenario.duration_s),
        skipped_event_types=skipped_types,
    )
    log.info("starting run: seed=%d duration=%s s", seed, scenario.duration_s)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        _process_events(
            scheduler,
            components,
            summary,
            events_path,
            scenario.duration_s,
            skipped_types,
        )
        write_summary(summary, summary_path)
    except OSError as error:
        _discard_output(events_path, summary_path)
        log.error("could not write run output to %s: %s", output_dir, error)
        raise RunError(f"could not write run output to {output_dir}") from error
    except BaseException:
        # Any other failure (a component error, Ctrl+C) also removes the
        # partial output, then propagates unchanged
        _discard_output(events_path, summary_path)
        raise

    log.info(
        "finished run: seed=%d events=%d pending=%d",
        scenario.master_seed,
        summary.events_processed,
        summary.events_pending,
    )
    return RunResult(
        summary=summary, events_path=events_path, summary_path=summary_path
    )
