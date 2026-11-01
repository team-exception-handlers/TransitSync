# AI contribution: 50% or more AI-generated
"""Decision audit: the numbers behind every hold decision (US-2.2, #44).

An error in the break-even calculation still gives results that look
reasonable (Risks page), so every decision is written out in full and can be
recalculated by hand. One record per decision holds:

- the observation values it was based on: L, H and each transfer group's
  M and s, plus F, the weights and the search settings
- the chosen hold and the reason
- every candidate with N(h), benefit, cost and J(h), and why it lost

Records go to ``decisions.jsonl`` next to the event log, one compact JSON
line each. They are not events: a record holds a list of candidates, while
event fields are flat, and keeping them apart leaves the event schema
unchanged. Key order is fixed and no wall-clock time or path is written, so
the file is byte-reproducible like the rest of the run output.

Design pattern: Collecting Parameter. A strategy gets a ``DecisionAuditLog``
and adds to it; the runner collects from every ``DecisionAuditSource`` once
the run ends, so no strategy touches the output files.
"""

import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from simulator.control.break_even import BreakEvenResult
from simulator.control.hold_search import HoldSearchResult
from simulator.engine.event_log import partial_path

DECISIONS_FILE = "decisions.jsonl"
# Bump when a record field is added, removed or renamed
DECISION_SCHEMA_VERSION = 1

# Why each candidate did or did not become the decision
OUTCOME_CHOSEN = "chosen"
OUTCOME_LOWER_NET = "lower net than chosen"
OUTCOME_TIED_LONGER = "same net as chosen, longer hold"


@runtime_checkable
class DecisionAuditSource(Protocol):
    """Anything that can hand the runner its decision records."""

    def decision_records(self) -> Sequence[dict[str, Any]]:
        """Return the records in the order the decisions were taken."""
        ...


class DecisionAuditLog:
    """Collects one record per decision during a run.

    A strategy calls ``record`` once per decision point, whether it holds or
    not, so declines are as visible as holds.
    """

    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []

    def record(self, result: HoldSearchResult) -> None:
        """Store the record for ``result``, built at once so it cannot change."""
        self._records.append(decision_record(result))

    def decision_records(self) -> tuple[dict[str, Any], ...]:
        """Return every record so far, oldest first."""
        return tuple(self._records)


def decision_record(result: HoldSearchResult) -> dict[str, Any]:
    """Return the audit record for one search, with a fixed key order."""
    inputs = result.inputs
    search = result.search
    # The candidate with the chosen length; h = 0 when no hold was chosen
    decision = next(c for c in result.candidates if c.hold_s == result.hold_s)
    return {
        "schema_version": DECISION_SCHEMA_VERSION,
        "time_s": inputs.time_s,
        "train_id": inputs.train_id,
        "station_id": inputs.station_id,
        "platform_id": inputs.platform_id,
        "inputs": {
            "load": inputs.load,
            "headway_s": inputs.headway_s,
            "transfers": [
                {
                    "group_id": group.group_id,
                    "group_size": group.group_size,
                    "conn_window_s": group.conn_window_s,
                }
                for group in inputs.transfers
            ],
        },
        "walking": _walking_record(search.walking),
        "weights": search.weights.to_dict(),
        "hold_search": search.settings.to_dict(),
        "chosen_hold_s": result.hold_s,
        "reason": result.reason,
        "candidates": [
            _candidate_record(candidate, decision) for candidate in result.candidates
        ],
    }


def candidate_outcome(candidate: BreakEvenResult, decision: BreakEvenResult) -> str:
    """Say why ``candidate`` was or was not the decision.

    The search keeps the highest J(h) and, on a tie, the shorter hold, so a
    candidate that lost either nets less or ties with a longer hold.
    """
    if candidate.hold_s == decision.hold_s:
        return OUTCOME_CHOSEN
    if candidate.net_ps < decision.net_ps:
        return OUTCOME_LOWER_NET
    return OUTCOME_TIED_LONGER


def _candidate_record(
    candidate: BreakEvenResult, decision: BreakEvenResult
) -> dict[str, Any]:
    return {
        "hold_s": candidate.hold_s,
        "n_caught": candidate.n_caught,
        "benefit_ps": candidate.benefit_ps,
        "cost_ps": candidate.cost_ps,
        "net_ps": candidate.net_ps,
        "worthwhile": candidate.worthwhile,
        "outcome": candidate_outcome(candidate, decision),
    }


def _walking_record(walking: object) -> dict[str, Any]:
    """Name the CDF family and its parameters, so F can be rebuilt by hand."""
    family = {"family": type(walking).__name__}
    # Both built-in CDFs are dataclasses; another implementation of the
    # protocol is still recorded by name rather than rejected
    if is_dataclass(walking) and not isinstance(walking, type):
        return family | asdict(walking)
    return family


def write_decision_log(records: Iterable[dict[str, Any]], path: Path) -> None:
    """Write ``records`` as JSON Lines, renaming into place only when complete.

    Raises:
        OSError: the file could not be written; the partial file is left for
            the runner to remove.
        ValueError: a record holds NaN or infinity, which JSON cannot store.
    """
    partial = partial_path(path)
    # newline="\n" keeps the bytes identical on Windows and Linux
    with partial.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(json.dumps(record, separators=(",", ":"), allow_nan=False))
            file.write("\n")
    partial.replace(path)
