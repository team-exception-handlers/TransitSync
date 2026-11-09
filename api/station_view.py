"""Apply the Adapter pattern to build the station-view API response.

The playback schema mirrors the frontend's station view. Passenger positions
are points on the selected transfer path; event and run times are seconds.
"""

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.passenger_tracks import build_passenger_tracks
from api.station_layout import (
    Connection,
    Platform,
    Point,
    StationLayoutResponse,
)
from api.time_utils import scenario_start_clock_s
from simulator.control.settings import OperatingRulesConfig
from simulator.engine.events import EventType
from simulator.passengers.transfer_component import TransferComponent
from simulator.scenario import Scenario

RULE_ORDER = ("max_hold_exceeded", "headway_violation", "one_hop_violation")
RULE_DESCRIPTIONS = {
    "max_hold_exceeded": (
        "Requested hold exceeds maximum hold time of {max_hold_time:g}s"
    ),
    "headway_violation": (
        "Hold would leave less than minimum safe gap of "
        "{min_safe_gap:g}s between trains"
    ),
    "one_hop_violation": "Target train for the connection is already system-delayed",
}


class PassengerSampleResponse(BaseModel):
    """One map position and phase at a simulation time measured in seconds.

    Position coordinates use the interchange map's pixel space.
    """

    model_config = ConfigDict(extra="forbid")

    time_s: float = Field(ge=0, allow_inf_nan=False)
    position: Point
    phase: Literal["walking", "queued", "waiting", "boarding", "boarded", "missed"]


class PassengerTrackResponse(BaseModel):
    """Map-ready samples for one passenger transfer through a connection.

    Samples are ordered by relative simulation time and retain their group ID.
    """

    model_config = ConfigDict(extra="forbid")

    passenger_id: str = Field(min_length=1)
    group_id: str = Field(min_length=1)
    connection_id: str = Field(min_length=1)
    samples: list[PassengerSampleResponse] = Field(min_length=1)


class TrainMovementResponse(BaseModel):
    """One train arrival or departure at a selected platform.

    Event and scheduled timestamps are shifted to the same run-relative origin.
    """

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["train_arrival", "train_departure"]
    train_id: str = Field(min_length=1)
    station_id: str = Field(min_length=1)
    platform_id: str = Field(min_length=1)
    time_s: float = Field(ge=0, allow_inf_nan=False)
    scheduled_s: float = Field(ge=0, allow_inf_nan=False)


class DecisionResponse(BaseModel):
    """The strategy's requested hold and the safety rules' applied hold.

    Hold durations and event time are seconds relative to the scenario start.
    """

    model_config = ConfigDict(extra="forbid")

    time_s: float = Field(ge=0, allow_inf_nan=False)
    train_id: str = Field(min_length=1)
    station_id: str = Field(min_length=1)
    platform_id: str = Field(min_length=1)
    requested_s: float = Field(ge=0, allow_inf_nan=False)
    applied_s: float = Field(ge=0, allow_inf_nan=False)
    reason: str = Field(min_length=1)


class OperatingRuleResponse(BaseModel):
    """One named operating rule and the action configured for it.

    Descriptions explain the rule in the same units as its configured limit.
    """

    model_config = ConfigDict(extra="forbid")

    name: Literal["max_hold_exceeded", "headway_violation", "one_hop_violation"]
    action: Literal["CLAMP", "REFUSE"]
    description: str = Field(min_length=1)


class OperatingRulesResponse(BaseModel):
    """The active rule limits and configured rule actions.

    Time limits use seconds; each named rule maps to its enforcement action.
    """

    model_config = ConfigDict(extra="forbid")

    max_hold_time: float = Field(gt=0, allow_inf_nan=False)
    min_safe_gap: float = Field(ge=0, allow_inf_nan=False)
    rule_action_map: dict[str, Literal["CLAMP", "REFUSE"]]


class SimulationRunResponse(StationLayoutResponse):
    """Station-view map data together with one run's dynamic playback records.

    ``start_clock_s`` is local clock time; event timestamps are relative seconds.
    """

    schema_version: Literal[1] = 1
    start_clock_s: float = Field(ge=0, allow_inf_nan=False)
    duration_s: float = Field(gt=0, allow_inf_nan=False)
    passenger_tracks: list[PassengerTrackResponse]
    train_events: list[TrainMovementResponse]
    decisions: list[DecisionResponse]
    rules: list[OperatingRuleResponse]
    operating_rules: OperatingRulesResponse


def build_station_view_response(
    layout: StationLayoutResponse,
    connection: Connection,
    scenario: Scenario,
    event_records: Sequence[dict[str, object]],
    transfers: TransferComponent,
) -> SimulationRunResponse:
    """Adapt static layout and simulator events to the station-view response.

    The validated response combines playback records with static map geometry.
    Passenger positions are interpolated along the selected connection corridor.
    """
    platform_by_id = {platform.platform_id: platform for platform in layout.platforms}
    shown_platforms = {connection.from_platform_id, connection.to_platform_id}
    response = SimulationRunResponse(
        **layout.model_dump(),
        schema_version=1,
        start_clock_s=scenario_start_clock_s(scenario),
        duration_s=float(scenario.duration_s),
        passenger_tracks=build_passenger_tracks(
            event_records,
            transfers,
            connection,
            platform_by_id,
            layout.corridors,
            float(scenario.duration_s),
        ),
        train_events=_train_events(event_records, shown_platforms, platform_by_id),
        decisions=_decision_records(event_records, shown_platforms),
        rules=_rule_records(scenario.operating_rules),
        operating_rules=scenario.operating_rules.to_dict(),
    )
    return response


def _train_events(
    records: Sequence[dict[str, object]],
    platform_ids: set[str],
    platforms: Mapping[str, Platform],
) -> list[dict[str, object]]:
    """Format selected-platform arrivals and departures for the frontend.

    Engine platform IDs are paired with the corresponding timetable stop IDs.
    """
    movement_types = {EventType.TRAIN_ARRIVAL.value, EventType.TRAIN_DEPARTURE.value}
    return [
        {
            "event_type": record["event_type"],
            "train_id": record["train_id"],
            "station_id": platforms[str(record["platform_id"])].stop_id,
            "platform_id": record["platform_id"],
            "time_s": record["time_s"],
            "scheduled_s": record["scheduled_s"],
        }
        for record in records
        if record.get("event_type") in movement_types
        and record.get("platform_id") in platform_ids
    ]


def _decision_records(
    records: Sequence[dict[str, object]], platform_ids: set[str]
) -> list[dict[str, object]]:
    """Expose applied hold events in the frontend's decision-record shape.

    Events outside the selected connection's two platforms are omitted.
    """
    fields = (
        "time_s",
        "train_id",
        "station_id",
        "platform_id",
        "requested_s",
        "applied_s",
        "reason",
    )
    return [
        {field: record[field] for field in fields}
        for record in records
        if record.get("event_type") == EventType.HOLD.value
        and record.get("platform_id") in platform_ids
    ]


def _rule_records(rules: OperatingRulesConfig) -> list[dict[str, str]]:
    """Create ordered, human-readable rule descriptions from configured limits."""
    records = []
    for name in RULE_ORDER:
        records.append(
            {
                "name": name,
                "action": rules.rule_action_map[name],
                "description": RULE_DESCRIPTIONS[name].format(
                    max_hold_time=rules.max_hold_time,
                    min_safe_gap=rules.min_safe_gap,
                ),
            }
        )
    return records
