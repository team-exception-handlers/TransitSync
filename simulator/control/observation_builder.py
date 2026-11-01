# AI contribution: 50% or more AI-generated
"""Observation builder: the read-only snapshot a strategy decides from.

Implements US-2.1, Task 2.1.2 (#38). Design pattern: Builder. It assembles an
``ObservationSnapshot`` at each ``DepartureDue`` from small read-only views of
the train and transfer components. The views return copies, so the snapshot
holds no references into simulator state.
"""

from collections.abc import Sequence
from typing import Protocol

from simulator.control.interface import (
    IncomingTransfer,
    ObservationSnapshot,
    PlatformState,
    TrainState,
)
from simulator.engine.events import DepartureDue


class TrainSource(Protocol):
    """Read-only view of trains and platforms (``TrainComponent``)."""

    def train_states(self) -> tuple[TrainState, ...]: ...

    def platform_states(self) -> tuple[PlatformState, ...]: ...


class TransferSource(Protocol):
    """Read-only view of walking transfer groups (``TransferComponent``)."""

    def incoming_transfers(self) -> tuple[IncomingTransfer, ...]: ...


class ObservationBuilder:
    """Builds snapshots from the trains plus any number of transfer sources."""

    def __init__(self, transfer_sources: Sequence[TransferSource] = ()) -> None:
        self._transfer_sources = tuple(transfer_sources)

    def build(self, decision: DepartureDue, trains: TrainSource) -> ObservationSnapshot:
        """Return what is true at ``decision``, before any prediction error."""
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
            trains=trains.train_states(),
            platforms=trains.platform_states(),
            incoming_transfers=transfers,
        )
