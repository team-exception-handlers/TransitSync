# AI contribution: 50% or more AI-generated
""" 
Times are simulation seconds. Reuse the shared passenger snapshots from #18 and
the live trains from #12. Doors are open from actual arrival through actual
departure; the engine's tie order permits an exact-departure-time connection.
Train capacity is enforced here; dwell/door-flow calibration is separate.
"""

from collections import Counter, defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from simulator.engine.event_queue import Scheduler
from simulator.engine.events import (
    Alighting,
    Boarding,
    Event,
    MissedConnection,
    PassengerArrival,
    TrainArrival,
    TrainDeparture,
)
from simulator.passengers.passenger import Passenger, PassengerState
from simulator.trains.train_component import TrainComponent


@dataclass(frozen=True, slots=True)
class _Visit:
    train_id: str
    platform_id: str
    destinations: frozenset[str]


class BoardingComponent:
    """Move tracked passengers between FIFO platform queues and train manifests.

    ``passengers`` is a shared dictionary, usually ``transfers.passengers``.
    Initially onboard passengers must be ON_BOARD, listed in ``initial_onboard``
    and included in their train's initial aggregate onboard_load. Untracked
    aggregate passengers retain their seats. Externally generated transfer
    alighting records identify entry into this passenger model, not a second
    subtraction from the feeder's aggregate load.
    """

    def __init__(
        self,
        trains: TrainComponent,
        passengers: dict[str, Passenger],
        *,
        initial_onboard: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        if not isinstance(trains, TrainComponent):
            raise ValueError("trains must be a TrainComponent")
        if not isinstance(passengers, dict) or any(
            not isinstance(p, Passenger) or key != p.passenger_id
            for key, p in passengers.items()
        ):
            raise ValueError("passengers must map passenger IDs to Passenger snapshots")
        self.trains = trains
        self.passengers = passengers
        self._onboard: dict[str, dict[str, None]] = {
            train_id: {} for train_id in trains.trains
        }
        self._load_initial(initial_onboard)
        self._waiting: dict[str, deque[str]] = defaultdict(deque)
        self._waiting_ids: set[str] = set()
        self._open: dict[str, _Visit] = {}
        self._departed: dict[str, list[tuple[_Visit, float]]] = defaultdict(list)
        self._connection_start: dict[str, float] = {}
        self._pending_boarding: dict[str, str] = {}
        self._pending_board_count: Counter[str] = Counter()
        self._pending_alighting: set[tuple[str, str]] = set()
        self._pending_alight_count: Counter[str] = Counter()
        self._external_alighted: set[tuple[str, str]] = set()
        self._missed: set[tuple[str, str, float]] = set()

    def _load_initial(self, initial: Mapping[str, Sequence[str]] | None) -> None:
        if initial is None:
            initial = {}
        if not isinstance(initial, Mapping):
            raise ValueError(
                "initial_onboard must map train IDs to passenger ID sequences"
            )
        seen: set[str] = set()
        for train_id, passenger_ids in initial.items():
            train = self.trains.trains.get(train_id)
            if train is None:
                raise ValueError("initial_onboard contains an unknown train ID")
            if isinstance(passenger_ids, str | bytes) or not isinstance(
                passenger_ids, Sequence
            ):
                raise ValueError(
                    "initial_onboard values must be passenger ID sequences"
                )
            if len(passenger_ids) > train.onboard_load:
                raise ValueError("initial_onboard exceeds the train's onboard_load")
            destinations = {
                s.station_id for s in train.schedule[train.current_stop_index :]
            }
            for passenger_id in passenger_ids:
                if not isinstance(passenger_id, str) or not passenger_id.strip():
                    raise ValueError("initial_onboard passenger IDs must be strings")
                passenger = self.passengers.get(passenger_id)
                if passenger is None or passenger_id in seen:
                    raise ValueError(
                        "initial_onboard passenger IDs must be known and unique"
                    )
                if passenger.state is not PassengerState.ON_BOARD:
                    raise ValueError("initial_onboard passengers must be ON_BOARD")
                if passenger.destination not in destinations:
                    raise ValueError(
                        "initial_onboard destination is not on the train route"
                    )
                seen.add(passenger_id)
                self._onboard[train_id][passenger_id] = None
        if seen != {
            p.passenger_id
            for p in self.passengers.values()
            if p.state is PassengerState.ON_BOARD
        }:
            raise ValueError("initial_onboard must identify every ON_BOARD passenger")

    @property
    def onboard(self) -> dict[str, tuple[str, ...]]:
        """Tracked passenger IDs per train; aggregate loads may also include others."""
        return {key: tuple(ids) for key, ids in self._onboard.items()}

    @property
    def waiting(self) -> dict[str, tuple[str, ...]]:
        """Queued IDs per platform in arrival order, excluding reserved boardings."""
        return {key: tuple(ids) for key, ids in self._waiting.items()}

    def start(self, scheduler: Scheduler) -> None:
        """Movement is triggered by train and passenger events, not timers."""

    def handle(self, event: Event, scheduler: Scheduler) -> None:
        if isinstance(event, TrainArrival) and event.train_id in self.trains.trains:
            self._on_arrival(event, scheduler)
        elif isinstance(event, PassengerArrival):
            self._on_passenger(event, scheduler)
        elif isinstance(event, Alighting):
            self._on_alighting(event)
        elif isinstance(event, Boarding):
            self._on_boarding(event)
        elif isinstance(event, TrainDeparture):
            self._on_departure(event, scheduler)

    def _on_arrival(self, event: TrainArrival, scheduler: Scheduler) -> None:
        train = self.trains.trains[event.train_id]
        self._open[train.id] = _Visit(
            train.id,
            event.platform_id,
            frozenset(
                s.station_id for s in train.schedule[train.current_stop_index + 1 :]
            ),
        )
        for passenger_id in self._onboard[train.id]:
            if self.passengers[passenger_id].destination == event.station_id:
                self._pending_alighting.add((train.id, passenger_id))
                self._pending_alight_count[train.id] += 1
                scheduler.schedule(
                    Alighting(
                        time_s=event.time_s,
                        passenger_id=passenger_id,
                        train_id=train.id,
                        platform_id=event.platform_id,
                    )
                )
        self._board_waiting(event.platform_id, scheduler)

    def _on_passenger(self, event: PassengerArrival, scheduler: Scheduler) -> None:
        passenger = self.passengers.get(event.passenger_id)
        if (
            passenger is None
            or passenger.state in (PassengerState.ON_BOARD, PassengerState.COMPLETED)
            or event.passenger_id in self._waiting_ids
            or event.passenger_id in self._pending_boarding
        ):
            return
        self.passengers[event.passenger_id] = replace(
            passenger, state=PassengerState.WAITING
        )
        self._waiting[event.platform_id].append(event.passenger_id)
        self._waiting_ids.add(event.passenger_id)
        for visit, closed_s in self._departed[event.platform_id]:
            if (
                self._connection_start.get(event.passenger_id, 0)
                <= closed_s
                < event.time_s
                and passenger.destination in visit.destinations
            ):
                self._mark_missed(event.passenger_id, visit, closed_s, scheduler)
                break
        self._board_waiting(event.platform_id, scheduler)

    def _board_waiting(self, platform: str, scheduler: Scheduler) -> None:
        remaining = deque()
        for passenger_id in self._waiting[platform]:
            destination = self.passengers[passenger_id].destination
            chosen = None
            for visit in self._open.values():
                train = self.trains.trains[visit.train_id]
                free = (
                    train.available_capacity
                    + self._pending_alight_count[train.id]
                    - self._pending_board_count[train.id]
                )
                if (
                    visit.platform_id == platform
                    and destination in visit.destinations
                    and free > 0
                ):
                    chosen = train.id
                    break
            if chosen is None:
                remaining.append(passenger_id)
                continue
            self._waiting_ids.remove(passenger_id)
            self._pending_boarding[passenger_id] = chosen
            self._pending_board_count[chosen] += 1
            scheduler.schedule(
                Boarding(
                    time_s=scheduler.now,
                    passenger_id=passenger_id,
                    train_id=chosen,
                    platform_id=platform,
                )
            )
        self._waiting[platform] = remaining

    def _on_alighting(self, event: Alighting) -> None:
        pair = (event.train_id, event.passenger_id)
        if pair in self._pending_alighting:
            self._pending_alighting.remove(pair)
            self._pending_alight_count[event.train_id] -= 1
            self.trains.alight_passenger(event.train_id)
            del self._onboard[event.train_id][event.passenger_id]
            self.passengers[event.passenger_id] = replace(
                self.passengers[event.passenger_id], state=PassengerState.COMPLETED
            )
        elif (
            event.passenger_id in self.passengers
            and pair not in self._external_alighted
        ):
            if self.passengers[event.passenger_id].state is PassengerState.WALKING:
                self._external_alighted.add(pair)
                self._connection_start[event.passenger_id] = event.time_s
                if event.train_id in self.trains.trains:
                    self.trains.record_external_alighting(event.train_id)

    def _on_boarding(self, event: Boarding) -> None:
        if self._pending_boarding.get(event.passenger_id) != event.train_id:
            return
        del self._pending_boarding[event.passenger_id]
        self._pending_board_count[event.train_id] -= 1
        self.trains.board_passenger(event.train_id)
        self._onboard[event.train_id][event.passenger_id] = None
        self.passengers[event.passenger_id] = replace(
            self.passengers[event.passenger_id], state=PassengerState.ON_BOARD
        )

    def _on_departure(self, event: TrainDeparture, scheduler: Scheduler) -> None:
        visit = self._open.pop(event.train_id, None)
        if visit is None:
            return
        self._departed[event.platform_id].append((visit, event.time_s))
        for passenger_id in self._waiting[event.platform_id]:
            if self.passengers[passenger_id].destination in visit.destinations:
                self._mark_missed(passenger_id, visit, event.time_s, scheduler)

    def _mark_missed(
        self, passenger_id: str, visit: _Visit, closed_s: float, scheduler: Scheduler
    ) -> None:
        key = (passenger_id, visit.train_id, closed_s)
        if key not in self._missed:
            self._missed.add(key)
            scheduler.schedule(
                MissedConnection(
                    time_s=scheduler.now,
                    passenger_id=passenger_id,
                    train_id=visit.train_id,
                    platform_id=visit.platform_id,
                )
            )
