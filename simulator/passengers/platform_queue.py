# AI contribution: 50% or more AI-generated
"""FIFO platform queues and passenger journeys (US-1.3, Task #100).

Mathematical Foundations §§4–5: movements determine train loads, and a waiting
queue conserves arrivals minus boardings. Times are seconds. TrainComponent
owns door-open intervals, including holds, and schedules the returned events.
"""

from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import replace

from simulator.engine.events import (
    Alighting,
    MissedConnection,
    PassengerArrival,
    TrainArrival,
    TrainDeparture,
)
from simulator.passengers.passenger import Passenger, PassengerState
from simulator.trains.train import Train


class PlatformQueue:
    """Own waiting passengers and optional destination-aware train manifests.

    Supply the shared transfers.passengers dictionary to track journeys.
    Initial manifests identify ON_BOARD passengers already included in train
    loads; untracked aggregate passengers keep their seats. Without a passenger
    dictionary, capacity-only FIFO boarding remains available. Build one queue
    per run; TrainComponent validates manifests when attaching the queue.
    Passenger states and movement records expose journey progress; internal
    manifest and queue containers remain private to this movement owner.
    No additional passenger component is registered with the event runner.
    """

    def __init__(
        self,
        platform_ids: tuple[str, ...],
        *,
        passengers: dict[str, Passenger] | None = None,
        initial_onboard: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        if any(not isinstance(item, str) or not item.strip() for item in platform_ids):
            raise ValueError("Platform IDs cannot be empty")
        if passengers is not None and (
            not isinstance(passengers, dict)
            or any(
                not isinstance(p, Passenger) or key != p.passenger_id
                for key, p in passengers.items()
            )
        ):
            raise ValueError("passengers must map passenger IDs to Passenger snapshots")
        if initial_onboard is not None and not isinstance(initial_onboard, Mapping):
            raise ValueError(
                "initial_onboard must map train IDs to passenger sequences"
            )
        if initial_onboard and passengers is None:
            raise ValueError("initial_onboard requires passengers")
        self.platform_ids = frozenset(platform_ids)
        self.passengers = passengers
        self._initial = initial_onboard or {}
        self._waiting: dict[str, deque[str]] = defaultdict(deque)
        self._seen: set[str] = set()
        self._onboard: dict[str, dict[str, None]] = {}
        self._alighted: dict[str, int] = defaultdict(int)
        self._departed: dict[str, list[tuple[TrainDeparture, frozenset[str]]]] = (
            defaultdict(list)
        )
        self._connection_start: dict[str, float] = {}
        self._missed: set[tuple[str, TrainDeparture]] = set()

    def bind_trains(self, trains: Mapping[str, Train]) -> None:
        """Validate initial identities against loads; no train loads change.

        Raises ValueError for missing, repeated, wrong-state or unreachable
        passengers. Initial passengers must already be counted in onboard_load.
        Validation finishes before any live manifest is installed.
        """
        seen: set[str] = set()
        for train_id, passenger_ids in self._initial.items():
            if train_id not in trains:
                raise ValueError("initial_onboard contains an unknown train ID")
            if isinstance(passenger_ids, str | bytes) or not isinstance(
                passenger_ids, Sequence
            ):
                raise ValueError("initial_onboard values must be ID sequences")
            if len(passenger_ids) > trains[train_id].onboard_load:
                raise ValueError("initial_onboard exceeds the train's onboard_load")
            for passenger_id in passenger_ids:
                self._check_initial(passenger_id, trains[train_id], seen)
                seen.add(passenger_id)
        if self.passengers is not None and seen != {
            p.passenger_id
            for p in self.passengers.values()
            if p.state is PassengerState.ON_BOARD
        }:
            raise ValueError("initial_onboard must identify every ON_BOARD passenger")
        self._onboard = {
            train_id: dict.fromkeys(self._initial.get(train_id, ()))
            for train_id in trains
        }

    def _check_initial(self, passenger_id: str, train: Train, seen: set[str]) -> None:
        """Check one identity before constructing any live manifest."""
        if not isinstance(passenger_id, str) or not passenger_id.strip():
            raise ValueError("initial_onboard passenger IDs must be strings")
        passenger = self.passengers.get(passenger_id) if self.passengers else None
        if passenger is None or passenger_id in seen:
            raise ValueError("initial_onboard passenger IDs must be known and unique")
        if passenger.state is not PassengerState.ON_BOARD:
            raise ValueError("initial_onboard passengers must be ON_BOARD")
        remaining = (train.schedule[train.current_stop_index :], *train.return_trips)
        if not any(
            stop.station_id == passenger.destination
            for trip in remaining
            for stop in trip
        ):
            raise ValueError("initial_onboard destination is not on the train route")

    def arrive(self, event: PassengerArrival) -> bool:
        """Enqueue an arrival; ignore unowned platforms and unknown passengers.

        Raises ValueError for duplicate accepted arrivals. Foreign events do not
        consume queue positions. The snapshot records reaching the platform.
        Completed or already onboard identities cannot start another arrival.
        """
        if event.platform_id not in self.platform_ids:
            return False
        if self.passengers is not None:
            passenger = self.passengers.get(event.passenger_id)
            if passenger is None or passenger.state in (
                PassengerState.ON_BOARD,
                PassengerState.COMPLETED,
            ):
                return False
        if event.passenger_id in self._seen:
            raise ValueError(f"Duplicate passenger arrival: {event.passenger_id}")
        self._seen.add(event.passenger_id)
        self._waiting[event.platform_id].append(event.passenger_id)
        self._set_state(event.passenger_id, PassengerState.WAITING)
        return True

    def waiting_count(self, platform_id: str) -> int:
        """Return passengers still waiting, including incompatible destinations."""
        return len(self._waiting[platform_id])

    def board(self, platform_id: str, train: Train) -> list[str]:
        """Board compatible passengers FIFO up to capacity; return their IDs.

        A passenger for another destination keeps their place without blocking
        compatible passengers behind them. TrainComponent calls this only while
        doors are open and emits the corresponding Boarding events.
        """
        boarded, remaining = [], deque()
        destinations = {
            stop.station_id for stop in train.schedule[train.current_stop_index + 1 :]
        }
        for passenger_id in self._waiting[platform_id]:
            compatible = self.passengers is None or (
                self.passengers[passenger_id].destination in destinations
            )
            if compatible and len(boarded) < train.available_capacity:
                boarded.append(passenger_id)
            else:
                remaining.append(passenger_id)
        train.board(len(boarded))
        self._waiting[platform_id] = remaining
        for passenger_id in boarded:
            if self.passengers is not None:
                self._onboard[train.id][passenger_id] = None
                self._set_state(passenger_id, PassengerState.ON_BOARD)
        return boarded

    def train_arrival(self, event: TrainArrival, train: Train) -> list[Alighting]:
        """Complete destination journeys before boarding; return alighting events.

        Called before a terminal arrival can advance the vehicle to a return
        trip, preserving the inbound platform and destination in the log.
        """
        self._alighted[train.id] = 0
        if self.passengers is None:
            return []
        leaving = [
            pid
            for pid in self._onboard[train.id]
            if self.passengers[pid].destination == event.station_id
        ]
        train.alight(len(leaving))
        self._alighted[train.id] = len(leaving)
        for passenger_id in leaving:
            del self._onboard[train.id][passenger_id]
            self._set_state(passenger_id, PassengerState.COMPLETED)
        return [
            Alighting(
                time_s=event.time_s,
                passenger_id=pid,
                train_id=train.id,
                platform_id=event.platform_id,
            )
            for pid in leaving
        ]

    def external_alighting(self, event: Alighting) -> None:
        """Record feeder entry without subtracting its aggregate load twice.

        Generated transfers were not previously included in the live train
        load. Their start time excludes trains that left before the walk began.
        """
        passenger = self.passengers.get(event.passenger_id) if self.passengers else None
        if (
            passenger is not None
            and passenger.state is PassengerState.WALKING
            and event.passenger_id not in self._connection_start
        ):
            self._connection_start[event.passenger_id] = event.time_s
            self._alighted[event.train_id] += 1

    def alighted_count(self, train_id: str) -> int:
        """Return passenger alightings at the vehicle's latest stop."""
        return self._alighted[train_id]

    def train_departure(
        self, event: TrainDeparture, train: Train
    ) -> list[MissedConnection]:
        """Remember closure; return misses for compatible passengers left behind.

        Snapshot the route before TrainComponent advances the vehicle. Actual
        closure times distinguish later visits by the same train, including
        return trips. A miss does not remove a passenger from the waiting queue.
        """
        if self.passengers is None:
            return []
        destinations = frozenset(
            stop.station_id for stop in train.schedule[train.current_stop_index + 1 :]
        )
        self._departed[event.platform_id].append((event, destinations))
        candidates = [
            self._missed_event(pid, event, destinations, event.time_s)
            for pid in self._waiting[event.platform_id]
        ]
        return [missed for missed in candidates if missed is not None]

    def late_arrival(self, event: PassengerArrival) -> list[MissedConnection]:
        """Return the first compatible miss since this transfer began.

        Exact-departure arrivals board first by the engine tie order. This path
        only considers trains that actually departed earlier than the arrival.
        """
        if self.passengers is None:
            return []
        start_s = self._connection_start.get(event.passenger_id, 0.0)
        for departure, destinations in self._departed[event.platform_id]:
            if start_s <= departure.time_s < event.time_s:
                missed = self._missed_event(
                    event.passenger_id, departure, destinations, event.time_s
                )
                if missed is not None:
                    return [missed]
        return []

    def _missed_event(
        self,
        passenger_id: str,
        departure: TrainDeparture,
        destinations: frozenset[str],
        time_s: float,
    ) -> MissedConnection | None:
        """Emit at most one miss per passenger and actual train visit."""
        key = (passenger_id, departure)
        if key in self._missed or (
            self.passengers[passenger_id].destination not in destinations
        ):
            return None
        self._missed.add(key)
        return MissedConnection(
            time_s=time_s,
            passenger_id=passenger_id,
            train_id=departure.train_id,
            platform_id=departure.platform_id,
        )

    def _set_state(self, passenger_id: str, state: PassengerState) -> None:
        """Replace immutable snapshots in the shared passenger dictionary."""
        if self.passengers is not None:
            passenger = self.passengers[passenger_id]
            self.passengers[passenger_id] = replace(passenger, state=state)
