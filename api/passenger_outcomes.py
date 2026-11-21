# AI contribution: 50% or more AI-generated
"""Passenger connection results from the ordered event log of one demo run."""

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


class PassengerComparison(BaseModel):
    """Passenger outcomes for the no-holding baseline and the selected strategy."""

    without_holding: list[PassengerOutcome]
    selected_strategy: list[PassengerOutcome]


def build_passenger_outcomes(
    records: Sequence[dict[str, object]], connection: Connection
) -> list[PassengerOutcome]:
    """Count services at the selected directional metro platform during each walk/wait.

    Use event order for ties so boarding at door closure catches that train.
    The simulator emits only the first missed_connection, and can emit it late.
    """
    outcomes: dict[str, PassengerOutcome] = {}
    starts: dict[str, int] = {}
    boardings: dict[str, int] = {}
    departures: list[int] = []
    departures_by_train: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        kind = record["event_type"]
        platform = record.get("platform_id")
        passenger = str(record.get("passenger_id", ""))
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
        first = bisect_left(departures, starts[passenger])
        end = bisect_left(departures, boardings.get(passenger, len(records)))
        missed = departures[first:end]
        outcome.missed_train_ids = [str(records[i]["train_id"]) for i in missed]
        if missed:
            outcome.status = "missed"
        if outcome.boarded_train_id is None:
            continue
        if not missed:
            outcome.status = "made"
            outcome.delay_s = 0.0
        visits = departures_by_train[outcome.boarded_train_id]
        visit = bisect_left(visits, boardings[passenger])
        if visit < len(visits):
            outcome.departure_s = float(records[visits[visit]]["time_s"])
            if missed:
                outcome.delay_s = outcome.departure_s - float(
                    records[missed[0]]["time_s"]
                )
    return [outcomes[pid] for pid in sorted(outcomes)]
