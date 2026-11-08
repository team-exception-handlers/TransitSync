# AI contribution: 50% or more AI-generated
"""Observation builder: the read-only snapshot a strategy decides from.

Implements US-2.1, Task 2.1.2 (#38). Design pattern: Builder. It assembles an
``ObservationSnapshot`` at each ``DepartureDue`` from small read-only views of
the train and transfer components. The views return copies, so the snapshot
holds no references into simulator state.
"""

import math
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from simulator.control.interface import (
    IncomingTransfer,
    ObservationSnapshot,
    PlatformState,
    TrainState,
)
from simulator.control.planning import FutureVisit
from simulator.engine.events import DepartureDue


class TrainSource(Protocol):
    """Read-only view of trains and platforms (``TrainComponent``)."""

    def train_states(self) -> tuple[TrainState, ...]: ...

    def platform_states(self) -> tuple[PlatformState, ...]: ...


class TransferSource(Protocol):
    """Read-only view of walking transfer groups (``TransferComponent``)."""

    def incoming_transfers(self) -> tuple[IncomingTransfer, ...]: ...


@runtime_checkable
class PlanningSource(TrainSource, Protocol):
    """Optional full-route view required by coordinated strategies (#61)."""

    def future_visits(
        self, now_s: float, until_s: float = math.inf
    ) -> tuple[FutureVisit, ...]: ...


class ObservationBuilder:
    """Builds snapshots from the trains plus any number of transfer sources."""

    def __init__(self, transfer_sources: Sequence[TransferSource] = ()) -> None:
        self._transfer_sources = tuple(transfer_sources)

    def build(
        self,
        decision: DepartureDue,
        trains: TrainSource,
        *,
        planning: bool = False,
        until_s: float = math.inf,
    ) -> ObservationSnapshot:
        """Return what is true at ``decision``, before any prediction error.

        ``until_s`` is an inclusive absolute simulation time in seconds. Pass
        the cutoff to the source so excluded visits are never materialized;
        it applies only when the controller requests a planning observation.
        """
        if planning and not isinstance(trains, PlanningSource):
            raise ValueError("coordinated planning requires a future-visits source")
        transfers = tuple(
            group
            for source in self._transfer_sources
            for group in source.incoming_transfers()
        )
        return ObservationSnapshot(
            time_s=decision.time_s,
            train_id=decision.train_id,
            station_id=decision.station_id,
            platform_id=decision.platform_id,
            scheduled_departure_s=decision.scheduled_s,
            trains=trains.train_states(),
            platforms=trains.platform_states(),
            incoming_transfers=transfers,
            future_visits=(
                trains.future_visits(decision.time_s, until_s) if planning else ()
            ),
            minimum_gap_s=getattr(trains, "minimum_gap_s", 90.0),
            suspensions=getattr(trains, "suspensions", ()),
        )
