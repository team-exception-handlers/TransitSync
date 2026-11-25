# AI contribution: 50% or more AI-generated
"""Passenger connection results from the ordered event log of one demo run,
and the same passengers matched across a paired comparison (#240)."""

from bisect import bisect_left
from collections import defaultdict
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from api.station_layout import Connection


class PassengerOutcome(BaseModel):
    """Times are seconds from run start. Missing events have null timestamps."""

    passenger_id: str
    connection_id: str
    alighting_s: float
    platform_arrival_s: float | None = None
    missed_train_ids: list[str] = Field(default_factory=list)
    boarded_train_id: str | None = None
    boarding_s: float | None = None
    departure_s: float | None = None
    transfer_time_s: float | None = Field(
        default=None, description="Elapsed time from feeder alighting to boarding."
    )
    delay_s: float | None = Field(
        default=None,
        description="Extra time from the first missed departure to actual departure, "
        "or zero when the first connection is made.",
    )
    status: Literal["made", "missed", "pending"] = "pending"


class MatchedPassenger(BaseModel):
    """One passenger in both runs; a side is null if that run never created them."""

    passenger_id: str
    selected_strategy: PassengerOutcome | None
    without_holding: PassengerOutcome | None


class PassengerComparison(BaseModel):
    """Each passenger's outcome with the selected strategy and without holding.

    The endpoint builds the list with ``match_passengers`` while it handles the
    request, so runs that are not a pair fail there and are logged. Each record
    holds both outcomes, so the response sends every outcome once.
    """

    matched_passengers: list[MatchedPassenger]


def _by_id(outcomes: Sequence[PassengerOutcome]) -> dict[str, PassengerOutcome]:
    """Index one run's outcomes, rejecting a passenger ID seen twice."""
    by_id = {outcome.passenger_id: outcome for outcome in outcomes}
    if len(by_id) != len(outcomes):
        raise ValueError("passenger outcomes repeat a passenger ID")
    return by_id


def match_passengers(
    selected: Sequence[PassengerOutcome], baseline: Sequence[PassengerOutcome]
) -> list[MatchedPassenger]:
    """Pair two runs' outcomes by passenger ID, which paired runs share (#240).

    A passenger can be in one run only, e.g. when a hold moves their feeder
    arrival past the run end or changes their group's size. One ID on two
    connections means the runs are not a pair, so it raises ``ValueError``.
    """
    held, base = _by_id(selected), _by_id(baseline)
    # Only IDs in both runs can disagree; one-run passengers are kept below
    for passenger_id in held.keys() & base.keys():
        if held[passenger_id].connection_id != base[passenger_id].connection_id:
            raise ValueError(f"passenger {passenger_id} is on two connections")
    # The union, so the frontend can say a passenger is absent from one run
    return [
        MatchedPassenger(
            passenger_id=passenger_id,
            selected_strategy=held.get(passenger_id),
            without_holding=base.get(passenger_id),
        )
        for passenger_id in sorted(held.keys() | base.keys())
    ]


def build_passenger_outcomes(
    records: Sequence[dict[str, object]], connection: Connection
) -> list[PassengerOutcome]:
    """Count services at the selected directional metro platform during each walk/wait.

    Use event order for ties so boarding at door closure catches that train.
    The simulator emits only the first missed_connection, and can emit it late.
    """
    # Positions in ``records``, not times, so same-time events keep their order
    outcomes: dict[str, PassengerOutcome] = {}
    starts: dict[str, int] = {}
    boardings: dict[str, int] = {}
    departures: list[int] = []
    departures_by_train: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        kind = record["event_type"]
        platform = record.get("platform_id")
        passenger = str(record.get("passenger_id", ""))
        # Alighting from the feeder starts an outcome; connecting platform
        # events (departures, arrival, boarding) fill it in
        if kind == "alighting" and platform == connection.from_platform_id:
            starts[passenger] = index
            outcomes[passenger] = PassengerOutcome(
                passenger_id=passenger,
                connection_id=connection.id,
                alighting_s=record["time_s"],
            )
        elif platform == connection.to_platform_id:
            if kind == "train_departure":
                departures.append(index)
                departures_by_train[str(record["train_id"])].append(index)
            elif passenger in outcomes:
                outcome = outcomes[passenger]
                if kind == "passenger_arrival":
                    outcome.platform_arrival_s = float(record["time_s"])
                elif kind == "boarding":
                    boardings[passenger] = index
                    outcome.boarded_train_id = str(record["train_id"])
                    outcome.boarding_s = float(record["time_s"])
                    outcome.transfer_time_s = outcome.boarding_s - outcome.alighting_s

    for passenger, outcome in outcomes.items():
        # A late walker’s first miss is only observed upon platform arrival.
        if outcome.platform_arrival_s is None:
            continue
        # Missed trains: departures after alighting and before boarding, or
        # before the run ends for a passenger who never boards
        first = bisect_left(departures, starts[passenger])
        end = bisect_left(departures, boardings.get(passenger, len(records)))
        missed = departures[first:end]
        outcome.missed_train_ids = [str(records[i]["train_id"]) for i in missed]
        if missed:
            outcome.status = "missed"
        if outcome.boarded_train_id is None:
            continue
        # No departure left without them, so they made their first connection
        if not missed:
            outcome.status = "made"
            outcome.delay_s = 0.0
        # Departure of the boarded train's first visit after this boarding
        visits = departures_by_train[outcome.boarded_train_id]
        visit = bisect_left(visits, boardings[passenger])
        if visit < len(visits):
            outcome.departure_s = float(records[visits[visit]]["time_s"])
            # Delay counts from the first train they missed to the one taken
            if missed:
                outcome.delay_s = outcome.departure_s - float(
                    records[missed[0]]["time_s"]
                )
    return [outcomes[pid] for pid in sorted(outcomes)]
