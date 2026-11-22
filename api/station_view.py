# AI contribution: 50% or more AI-generated
"""Apply the Adapter pattern to build the station-view API response.

The playback schema mirrors the frontend's station view. Passenger positions
are points on the selected transfer path; event and run times are seconds.
The existing response models and adapters exceed 500 lines; keep this edit
local to streaming audit consumption while parallel results work integrates.
"""

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from api.passenger_metrics import PassengerMetrics, compute_passenger_metrics
from api.passenger_outcomes import PassengerOutcome, build_passenger_outcomes
from api.passenger_tracks import build_passenger_tracks
from api.station_layout import (
    Connection,
    Platform,
    Point,
    StationLayoutResponse,
)
from api.time_utils import scenario_start_clock_s
from simulator.control.decision_audit import KIND_ESTIMATES, KIND_MODE_SWITCH
from simulator.control.settings import OperatingRulesConfig
from simulator.control.validation import find_rule_violations
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


class ModeSwitchResponse(BaseModel):
    """One change of policy by the adaptive strategy (#60).

    Adaptive protects connections until the recent mean headway deviation on a
    line and platform rises above the irregularity threshold, then regulates
    headways instead, and switches back when it falls again. ``time_s`` is in
    seconds from the run start; the deviation and threshold are dimensionless
    (a fraction of the target gap between trains).
    """

    model_config = ConfigDict(extra="forbid")

    time_s: float = Field(ge=0, allow_inf_nan=False)
    train_id: str = Field(min_length=1)
    station_id: str = Field(min_length=1)
    platform_id: str = Field(min_length=1)
    line_id: str = Field(min_length=1)
    from_mode: Literal["connection_protection", "headway_regulation"]
    to_mode: Literal["connection_protection", "headway_regulation"]
    service_irregularity: float = Field(ge=0, allow_inf_nan=False)
    irregularity_threshold: float = Field(ge=0, allow_inf_nan=False)


class SeenTrueResponse(BaseModel):
    """A value as the strategy saw it (with prediction error) and its truth.

    Both are null when there was nothing to predict.
    """

    model_config = ConfigDict(extra="forbid")

    seen: float | None = Field(allow_inf_nan=False)
    true: float | None = Field(allow_inf_nan=False)


class EstimatedTrainResponse(BaseModel):
    """The held train's estimated arrival and onboard load."""

    model_config = ConfigDict(extra="forbid")

    train_id: str = Field(min_length=1)
    predicted_arrival_s: SeenTrueResponse
    onboard_load: SeenTrueResponse


class EstimatedTransferResponse(BaseModel):
    """One transfer group's still-walking count and its total size."""

    model_config = ConfigDict(extra="forbid")

    group_id: str = Field(min_length=1)
    passenger_count: SeenTrueResponse
    group_size: SeenTrueResponse


class EstimatesResponse(BaseModel):
    """What the strategy saw at one shown hold, next to the true values (#39).

    The gap between seen and true grows with the run's error magnitude.
    """

    model_config = ConfigDict(extra="forbid")

    time_s: float = Field(ge=0, allow_inf_nan=False)
    train_id: str = Field(min_length=1)
    station_id: str = Field(min_length=1)
    platform_id: str = Field(min_length=1)
    trains: list[EstimatedTrainResponse]
    transfers: list[EstimatedTransferResponse]


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


class RuleViolationResponse(BaseModel):
    """One place where the run's event log broke an operating rule.

    ``subject_id`` is the held train or the platform with the short gap.
    """

    model_config = ConfigDict(extra="forbid")

    rule: Literal["max_hold_exceeded", "headway_violation"]
    time_s: float = Field(ge=0, allow_inf_nan=False)
    subject_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class RuleCheckResponse(BaseModel):
    """The post-run check of the whole event log against the run's limits."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    violations: list[RuleViolationResponse]


class DelayBucketResponse(BaseModel):
    """Average passenger waiting delay in one five-minute simulation bucket."""

    model_config = ConfigDict(extra="forbid")

    start_s: float = Field(ge=0, allow_inf_nan=False)
    end_s: float = Field(gt=0, allow_inf_nan=False)
    average_passenger_delay_s: float = Field(ge=0, allow_inf_nan=False)
    passenger_count: int = Field(ge=0)


class HoldEventResponse(BaseModel):
    """One applied hold that the delay chart can mark on its time axis."""

    model_config = ConfigDict(extra="forbid")

    time_s: float = Field(ge=0, allow_inf_nan=False)
    train_id: str = Field(min_length=1)
    station_id: str = Field(min_length=1)
    platform_id: str = Field(min_length=1)
    applied_s: float = Field(gt=0, allow_inf_nan=False)


class TimeSeriesResponse(BaseModel):
    """Passenger delay and hold events for the complete run horizon."""

    model_config = ConfigDict(extra="forbid")

    start_s: float = Field(ge=0, allow_inf_nan=False)
    end_s: float = Field(gt=0, allow_inf_nan=False)
    bucket_s: float = Field(gt=0, allow_inf_nan=False)
    buckets: list[DelayBucketResponse]
    hold_events: list[HoldEventResponse]


class SimulationRunResponse(StationLayoutResponse):
    """Station-view map data together with one run's dynamic playback records.

    ``start_clock_s`` is local clock time; event timestamps are relative seconds.
    """

    schema_version: Literal[1] = 1
    start_clock_s: float = Field(ge=0, allow_inf_nan=False)
    duration_s: float = Field(gt=0, allow_inf_nan=False)
    passenger_tracks: list[PassengerTrackResponse]
    passenger_outcomes: list[PassengerOutcome] = Field(default_factory=list)
    passenger_metrics: PassengerMetrics = Field(
        default_factory=lambda data: compute_passenger_metrics(
            data["passenger_outcomes"]
        )
    )
    train_events: list[TrainMovementResponse]
    decisions: list[DecisionResponse]
    # Empty for every strategy except adaptive. Added without a schema bump
    # because older clients ignore the extra key and the default keeps cached
    # payloads without it valid.
    mode_switches: list[ModeSwitchResponse] = Field(default_factory=list)
    # One per shown decision; optional for the same reason as mode_switches
    estimates: list[EstimatesResponse] = Field(default_factory=list)
    rules: list[OperatingRuleResponse]
    operating_rules: OperatingRulesResponse
    # Optional for the same reason as mode_switches: cached payloads lack it.
    rule_check: RuleCheckResponse | None = None
    time_series: TimeSeriesResponse | None = None


def build_station_view_response(
    layout: StationLayoutResponse,
    connection: Connection,
    scenario: Scenario,
    event_records: Sequence[dict[str, object]],
    transfers: TransferComponent,
    decision_records: Iterable[dict[str, object]] = (),
) -> SimulationRunResponse:
    """Adapt static layout and simulator events to the station-view response.

    The validated response combines playback records with static map geometry.
    Passenger positions are interpolated along the selected connection corridor.
    ``decision_records`` are the run's decision-audit records; adaptive mode
    switches and the estimates behind each shown decision are read from them.
    """
    platform_by_id = {platform.platform_id: platform for platform in layout.platforms}
    shown_platforms = {connection.from_platform_id, connection.to_platform_id}
    decisions = _decision_records(event_records, shown_platforms)
    timeline_holds = []
    mode_switches, estimates = _playback_audit(
        decision_records, decisions, shown_platforms, hold_records=timeline_holds
    )
    response = SimulationRunResponse(
        **layout.model_dump(),
        schema_version=1,
        start_clock_s=scenario_start_clock_s(scenario),
        duration_s=float(scenario.duration_s),
        passenger_outcomes=build_passenger_outcomes(event_records, connection),
        passenger_tracks=build_passenger_tracks(
            event_records,
            transfers,
            connection,
            platform_by_id,
            layout.corridors,
            float(scenario.duration_s),
        ),
        train_events=_train_events(event_records, shown_platforms, platform_by_id),
        decisions=decisions,
        mode_switches=mode_switches,
        estimates=estimates,
        rules=_rule_records(scenario.operating_rules),
        operating_rules=scenario.operating_rules.to_dict(),
        rule_check=_rule_check(event_records, scenario.operating_rules),
        time_series=_time_series_records(
            event_records,
            timeline_holds,
            float(scenario.duration_s),
            shown_platforms,
        ),
    )
    return response


def _playback_audit(records, decisions, platform_ids, *, hold_records=None):
    """Read audit lines once, retaining only data actually displayed in playback.

    Full-network estimate records can dwarf the passenger event log. Feed them
    directly through the existing adapter rather than retaining every train at
    every decision. Mode switches are small and keep their original stable sort.
    """
    switches = []

    def estimates():
        for record in records:
            if record.get("kind") == KIND_MODE_SWITCH:
                switches.append(record)
            if hold_records is not None and record.get("kind") == "hold":
                # The time-series adapter needs these small records after this
                # iterator is consumed; never retain full-network estimates.
                hold_records.append(record)
            yield record

    shown_estimates = _estimate_records(estimates(), decisions)
    return _mode_switch_records(switches, platform_ids), shown_estimates


def _rule_check(
    records: Sequence[dict[str, object]], rules: OperatingRulesConfig
) -> RuleCheckResponse:
    """Check every event in the run, not only the shown connection's platforms.

    Uses the run's own limits, so a chosen maximum hold below 300 s is the one
    each hold is checked against.
    """
    found = find_rule_violations(records, rules.max_hold_time, rules.min_safe_gap)
    return RuleCheckResponse(
        passed=not found,
        violations=[RuleViolationResponse(**asdict(item)) for item in found],
    )


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


def _mode_switch_records(
    records: Sequence[dict[str, object]], platform_ids: set[str]
) -> list[dict[str, object]]:
    """Keep the adaptive mode switches on the selected connection's platforms.

    Adaptive decides per line and platform across the whole network, so one run
    holds switches at all three interchanges; only the two platforms the
    station view shows are kept, as for hold decisions. Audit records are not
    written in time order, so the result is sorted by time (stable for ties).
    """
    fields = (
        "time_s",
        "train_id",
        "station_id",
        "platform_id",
        "line_id",
        "from_mode",
        "to_mode",
        "service_irregularity",
        "irregularity_threshold",
    )
    switches = [
        {field: record[field] for field in fields}
        for record in records
        if record.get("kind") == KIND_MODE_SWITCH
        and record.get("platform_id") in platform_ids
    ]
    return sorted(switches, key=lambda switch: cast(float, switch["time_s"]))


def _estimate_records(
    records: Iterable[dict[str, object]], decisions: Sequence[dict[str, object]]
) -> list[dict[str, object]]:
    """Keep the estimates taken at each shown decision, cut to that decision.

    The pipeline records every train in the network at every decision (often
    over a thousand), so each record is cut to the held train and the
    transfer groups walking to its platform. The held train is at the
    platform, so only its load is kept: its next arrival is outside the view.
    """
    shown = {
        (decision["time_s"], decision["train_id"], decision["platform_id"])
        for decision in decisions
    }
    kept = []
    for record in records:
        key = (record.get("time_s"), record.get("train_id"), record.get("platform_id"))
        if record.get("kind") != KIND_ESTIMATES or key not in shown:
            continue
        trains = cast(list[dict[str, object]], record["trains"])
        kept.append(
            {
                "time_s": record["time_s"],
                "train_id": record["train_id"],
                "station_id": record["station_id"],
                "platform_id": record["platform_id"],
                "trains": [
                    {**train, "predicted_arrival_s": {"seen": None, "true": None}}
                    for train in trains
                    if train["train_id"] == record["train_id"]
                ],
                "transfers": record["transfers"],
            }
        )
    return kept


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


def _time_series_records(
    event_records: Sequence[dict[str, object]],
    decision_records: Sequence[dict[str, object]],
    duration_s: float,
    platform_ids: set[str],
) -> dict[str, object]:
    """Aggregate passenger platform waiting and applied holds over five-minute buckets.

    Passenger delay is the time from reaching a selected-platform queue to boarding
    or being marked missed. Waiting with no terminal event contributes no delay
    value; every bucket still exists so the chart represents the full horizon.
    """
    bucket_s = 300.0
    bucket_count = max(1, math.ceil(duration_s / bucket_s))
    totals = [0.0] * bucket_count
    counts = [0] * bucket_count
    events_by_passenger: dict[str, list[dict[str, object]]] = {}
    for record in event_records:
        passenger_id = record.get("passenger_id")
        if isinstance(passenger_id, str):
            events_by_passenger.setdefault(passenger_id, []).append(record)

    for passenger_events in events_by_passenger.values():
        arrival = next(
            (
                record
                for record in passenger_events
                if record.get("event_type") == EventType.PASSENGER_ARRIVAL.value
                and record.get("platform_id") in platform_ids
            ),
            None,
        )
        terminal = next(
            (
                record
                for record in passenger_events
                if record.get("event_type")
                in {EventType.BOARDING.value, EventType.MISSED_CONNECTION.value}
                and record.get("platform_id") in platform_ids
            ),
            None,
        )
        if arrival is None or terminal is None:
            continue
        arrival_s = float(arrival["time_s"])
        terminal_s = float(terminal["time_s"])
        if not arrival_s <= terminal_s <= duration_s:
            continue
        bucket = min(int(terminal_s // bucket_s), bucket_count - 1)
        totals[bucket] += max(0.0, terminal_s - arrival_s)
        counts[bucket] += 1

    buckets = []
    for index in range(bucket_count):
        start_s = index * bucket_s
        end_s = min((index + 1) * bucket_s, duration_s)
        average = totals[index] / counts[index] if counts[index] else 0.0
        buckets.append(
            {
                "start_s": start_s,
                "end_s": end_s,
                "average_passenger_delay_s": average,
                "passenger_count": counts[index],
            }
        )

    hold_events = sorted(
        (
            {
                "time_s": record["time_s"],
                "train_id": record["train_id"],
                "station_id": record["station_id"],
                "platform_id": record["platform_id"],
                "applied_s": record["applied_s"],
            }
            for record in decision_records
            if record.get("kind") == "hold"
            and record.get("platform_id") in platform_ids
            and float(record.get("applied_s", 0)) > 0
        ),
        key=lambda event: cast(float, event["time_s"]),
    )
    # Decision audit records use hold events too, but mode-switch records remain
    # separate; this fallback accepts raw hold-event records from the engine log.
    if not hold_events:
        hold_events = sorted(
            (
                {
                    "time_s": record["time_s"],
                    "train_id": record["train_id"],
                    "station_id": record["station_id"],
                    "platform_id": record["platform_id"],
                    "applied_s": record["applied_s"],
                }
                for record in event_records
                if record.get("event_type") == EventType.HOLD.value
                and record.get("platform_id") in platform_ids
                and float(record.get("applied_s", 0)) > 0
            ),
            key=lambda event: cast(float, event["time_s"]),
        )

    return {
        "start_s": 0.0,
        "end_s": duration_s,
        "bucket_s": bucket_s,
        "buckets": buckets,
        "hold_events": hold_events,
    }
