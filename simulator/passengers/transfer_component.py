# AI contribution: 50% or more AI-generated
"""Mathematical Foundations section 2: create a whole group at a feeder arrival,
then apply individual walking times. Section 5: enter the corridor in simulation
time order, including when walks from different groups overlap. Times are seconds.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import NamedTuple

from simulator.control.interface import IncomingTransfer
from simulator.engine.event_queue import Scheduler
from simulator.engine.events import (
    Alighting,
    Boarding,
    CorridorArrival,
    Event,
    PassengerArrival,
    TrainArrival,
)
from simulator.engine.random_streams import StreamManager
from simulator.engine.walking_sampler import WalkingTimeSampler
from simulator.passengers.corridor import CorridorPassage, CorridorQueue
from simulator.passengers.demand import DemandProfile, _nonnegative_number
from simulator.passengers.generation import (
    PassengerGenerator,
    _destination_distribution,
)
from simulator.passengers.passenger import Passenger, PassengerState


class _Walk(NamedTuple):
    """One passenger's walk, with the group facts a strategy needs (#41)."""

    group_id: str
    platform_id: str
    end_s: float
    feeder_arrival_s: float
    group_size: int


@dataclass(frozen=True, slots=True)
class TransferRoute:
    """One feeder platform and connecting platform at an interchange.

    Demand accumulates from ``demand_start_s`` to the first actual feeder arrival,
    then between consecutive actual arrivals on this route. Fractions describe
    final destination stations, not the interchange's connecting platform. Share
    a ``CorridorQueue`` instance between routes using the same physical bottleneck.
    """

    station_id: str
    feeder_platform_id: str
    connecting_platform_id: str
    demand_profile: DemandProfile
    transfer_fractions: Mapping[str, float]
    corridor: CorridorQueue
    walking_mean_s: float = 300.0
    walking_min_s: float = 30.0
    demand_start_s: float = 0.0

    def __post_init__(self) -> None:
        for name in ("station_id", "feeder_platform_id", "connecting_platform_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"TransferRoute.{name} must be a non-empty string")
            object.__setattr__(self, name, value.strip())
        if self.feeder_platform_id == self.connecting_platform_id:
            raise ValueError(
                "connecting_platform_id must differ from feeder_platform_id"
            )
        if not isinstance(self.demand_profile, DemandProfile):
            raise ValueError("demand_profile must be a DemandProfile")
        if not isinstance(self.corridor, CorridorQueue):
            raise ValueError("corridor must be a CorridorQueue")
        for name in ("walking_mean_s", "walking_min_s", "demand_start_s"):
            object.__setattr__(
                self, name, _nonnegative_number(getattr(self, name), name)
            )
        if self.walking_mean_s <= self.walking_min_s:
            raise ValueError("walking_mean_s must exceed walking_min_s")
        destinations, probabilities = _destination_distribution(
            self.station_id, self.transfer_fractions
        )
        object.__setattr__(
            self,
            "transfer_fractions",
            MappingProxyType(dict(zip(destinations, probabilities, strict=True))),
        )


class TransferComponent:
    """Release transfers only in response to actual ``TrainArrival`` events.

    Construct fresh routes/corridors and one component per run. Multiple transfer
    components need distinct ``id_prefix`` values. Passenger snapshots follow
    walks and boarding events emitted by the existing platform queue; destination
    alighting and missed connections remain boarding logic's responsibility (#100).
    Feeder demand is external: it is not subtracted from aggregate train loads.
    """

    def __init__(
        self,
        routes: Sequence[TransferRoute],
        stream_manager: StreamManager,
        *,
        id_prefix: str = "passenger",
    ) -> None:
        if (
            isinstance(routes, str | bytes)
            or not isinstance(routes, Sequence)
            or any(not isinstance(route, TransferRoute) for route in routes)
        ):
            raise ValueError("routes must be a sequence of TransferRoute")
        self._routes: dict[tuple[str, str], TransferRoute] = {}
        for route in routes:
            key = (route.station_id, route.feeder_platform_id)
            if key in self._routes:
                raise ValueError(
                    "routes must have unique station/feeder platform pairs"
                )
            self._routes[key] = route
        self._last_arrival = {
            key: route.demand_start_s for key, route in self._routes.items()
        }
        self._generator = PassengerGenerator(stream_manager, id_prefix=id_prefix)
        self._walking_sampler = WalkingTimeSampler(stream_manager)
        self._id_prefix = id_prefix
        self._next_group = 1
        self._walking_routes: dict[str, TransferRoute] = {}
        # passenger_id -> walk still in progress
        self._walks: dict[str, _Walk] = {}
        self.passengers: dict[str, Passenger] = {}
        self.passages: dict[str, CorridorPassage] = {}

    def start(self, scheduler: Scheduler) -> None:
        """Schedule nothing: without feeder trains there are no passenger pulses."""

    def incoming_transfers(self) -> tuple[IncomingTransfer, ...]:
        """Passengers still walking, grouped by transfer group (#38).

        Times are when each walk ends at the corridor, before any queueing.
        Every walk in a group shares its feeder arrival time and group size.
        """
        groups: dict[tuple[str, str], list[_Walk]] = {}
        for walk in self._walks.values():
            groups.setdefault((walk.group_id, walk.platform_id), []).append(walk)
        return tuple(
            IncomingTransfer(
                group_id,
                platform_id,
                len(walks),
                min(walk.end_s for walk in walks),
                max(walk.end_s for walk in walks),
                walks[0].feeder_arrival_s,
                walks[0].group_size,
            )
            for (group_id, platform_id), walks in sorted(groups.items())
        )

    def handle(self, event: Event, scheduler: Scheduler) -> None:
        """Advance groups, walks and platform arrivals through the event queue."""
        if isinstance(event, TrainArrival):
            self._on_train_arrival(event, scheduler)
        elif isinstance(event, CorridorArrival):
            self._on_corridor_arrival(event, scheduler)
        elif isinstance(event, PassengerArrival):
            if event.passenger_id in self.passages:
                passenger = self.passengers[event.passenger_id]
                if passenger.state is PassengerState.WALKING:
                    self.passengers[event.passenger_id] = replace(
                        passenger, state=PassengerState.WAITING
                    )
        elif isinstance(event, Boarding) and event.passenger_id in self.passengers:
            passenger = self.passengers[event.passenger_id]
            self.passengers[event.passenger_id] = replace(
                passenger, state=PassengerState.ON_BOARD
            )

    def _on_train_arrival(self, event: TrainArrival, scheduler: Scheduler) -> None:
        key = (event.station_id, event.platform_id)
        route = self._routes.get(key)
        if route is None or event.time_s < route.demand_start_s:
            return
        passengers = self._generator.generate(
            origin=route.station_id,
            demand_profile=route.demand_profile,
            start_s=self._last_arrival[key],
            end_s=event.time_s,
            transfer_fractions=route.transfer_fractions,
        )
        self._last_arrival[key] = event.time_s
        if passengers:
            self._release_group(passengers, route, event, scheduler)

    def _release_group(
        self,
        passengers: list[Passenger],
        route: TransferRoute,
        event: TrainArrival,
        scheduler: Scheduler,
    ) -> None:
        group_id = f"{self._id_prefix}-group-{self._next_group:06d}"
        self._next_group += 1
        walks = self._walking_sampler.sample(
            size=len(passengers),
            mean=route.walking_mean_s,
            min_time=route.walking_min_s,
        )
        for passenger, walk_s in zip(passengers, walks, strict=True):
            passenger_id = passenger.passenger_id
            self.passengers[passenger_id] = replace(
                passenger, state=PassengerState.WALKING
            )
            self._walking_routes[passenger_id] = route
            walk_end_s = event.time_s + float(walk_s)
            platform_id = route.connecting_platform_id
            self._walks[passenger_id] = _Walk(
                group_id, platform_id, walk_end_s, event.time_s, len(passengers)
            )
            scheduler.schedule(
                Alighting(
                    time_s=event.time_s,
                    passenger_id=passenger_id,
                    train_id=event.train_id,
                    platform_id=event.platform_id,
                )
            )
            scheduler.schedule(
                CorridorArrival(
                    time_s=walk_end_s,
                    passenger_id=passenger_id,
                    group_id=group_id,
                    platform_id=route.connecting_platform_id,
                )
            )

    def _on_corridor_arrival(
        self, event: CorridorArrival, scheduler: Scheduler
    ) -> None:
        route = self._walking_routes.pop(event.passenger_id, None)
        self._walks.pop(event.passenger_id, None)
        if route is None:
            return
        passage = route.corridor.admit(event.passenger_id, event.time_s)
        self.passages[event.passenger_id] = passage
        scheduler.schedule(
            PassengerArrival(
                time_s=passage.passage_s,
                passenger_id=event.passenger_id,
                group_id=event.group_id,
                platform_id=route.connecting_platform_id,
            )
        )
