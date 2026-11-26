# AI contribution: 50% or more AI-generated
"""Run committed demo scenarios and cache their map-ready API responses.

The API selects scenario files by connection ID, applies validated request
settings, then delegates event processing to the simulator. Simulation time
and every hold duration are expressed in seconds.

This module exceeds 500 lines because validation, caching and the component
factory share scenario assembly. The audit readers below stay here, beside
the run that writes them, rather than starting a split in a performance PR.
"""

from __future__ import annotations

import json
import logging
import statistics
import tempfile
from collections import OrderedDict, defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import Future
from copy import deepcopy
from dataclasses import replace
from functools import partial
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import from_json

from api.connection_data import index_connections
from api.network_data import DATASET_ID, dataset_metadata, load_reference_network
from api.run_results import RunResultsResponse
from api.station_layout import Connection, StationLayoutResponse
from api.station_layout import Platform as LayoutPlatform
from api.station_view import SimulationRunResponse, build_station_view_response
from api.time_utils import scenario_start_clock_s
from simulator.control.connection_configuration import (
    build_selected_connection_protection,
)
from simulator.control.decision import DecisionPipeline
from simulator.control.decision_audit import KIND_ESTIMATES, EncodedDecisionRecord
from simulator.control.headway_configuration import validate_headway_configuration
from simulator.control.observation_builder import ObservationBuilder
from simulator.control.prediction_error import (
    PredictionErrorModel,
    PredictionErrorSettings,
)
from simulator.control.rules import OperatingRulesEnforcer
from simulator.control.settings import (
    CONNECTION_HEADWAY_STRATEGIES,
    TARGET_HEADWAY_STRATEGIES,
)
from simulator.control.strategies import STRATEGIES
from simulator.control.strategies.adaptive import AdaptiveStrategy
from simulator.control.walking_cdf import ShiftedExponentialCdf
from simulator.disruptions import get_disruption_preset
from simulator.engine.events import EventType
from simulator.engine.random_streams import StreamManager
from simulator.engine.runner import Component, run_scenario
from simulator.network_config import NetworkConfig
from simulator.passengers import (
    CorridorQueue,
    DemandPeriod,
    DemandProfile,
    TransferComponent,
    TransferRoute,
)
from simulator.passengers.platform_queue import PlatformQueue
from simulator.scenario import Scenario, load_scenario_file
from simulator.timetable import ScheduledVisit
from simulator.trains.disruption import DelayInjection
from simulator.trains.spacing import perturb_dispatch_times
from simulator.trains.suspension import LineSuspension
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent

log = logging.getLogger(__name__)

CONFIG_ROOT = Path(__file__).resolve().parents[1] / "config"
SCENARIO_PATHS = {
    interchange_id: CONFIG_ROOT / "scenarios" / f"{interchange_id}.json"
    for interchange_id in (
        "gare_centrale_bonaventure",
        "mcgill",
        "edouard_montpetit",
    )
}
TRAIN_CAPACITY = 800
WALKING_MEAN_S = 120.0
WALKING_MIN_S = 30.0
CORRIDOR_CAPACITY_PER_MINUTE = 60.0
DEMAND_RATES_PER_MINUTE = {"Low": 6.0, "Normal": 12.0, "High": 24.0}
MAX_CACHED_RUNS = 8
# The STM GTFS feed gives every metro stop the same arrival and departure time,
# so trains would open their doors for 0 s. Assumed dwell until it is measured.
MIN_STOP_DWELL_S = 30.0
# Passengers already on board each train (L in the break-even cost). With 0,
# holding looked free and connection protection always held the maximum.
# Assumed, as no load data exists yet.
ONBOARD_LOAD = 300


class SimulationRunRequest(BaseModel):
    """Validated options for one fixed-duration demo run.

    ``max_hold_time`` is in seconds, in five-second increments up to 300.
    ``error_magnitude`` is the prediction-error kappa shared by all estimates,
    bounded from 0 to 3.
    Passenger-flow labels map to fixed passenger-per-minute demand rates.
    Unknown fields are rejected so misspelled controls cannot be ignored.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    connection_id: str = Field(min_length=1, max_length=128, strict=True)
    strategy: str = Field(
        default="no_control", min_length=1, max_length=64, strict=True
    )
    max_hold_time: float = Field(
        default=300.0,
        gt=0,
        le=300,
        multiple_of=5,
        allow_inf_nan=False,
        strict=True,
    )
    error_magnitude: float = Field(
        default=1.0, ge=0, le=3, allow_inf_nan=False, strict=True
    )
    passenger_flow: Literal["Low", "Normal", "High"] = "Normal"
    disruption_enabled: bool = Field(default=False, strict=True)
    disruption_preset: Literal[
        "none", "platform_delay", "line_suspension", "uneven_headways"
    ] = "none"
    disruption_time_s: float = Field(
        default=120.0, ge=0, allow_inf_nan=False, strict=True
    )
    disruption_magnitude: float = Field(
        default=60.0, gt=0, allow_inf_nan=False, strict=True
    )

    irregularity_threshold: float | None = Field(
        default=None, ge=0, allow_inf_nan=False, strict=True
    )

    @property
    def run_id(self) -> str:
        """Identify this settings combination in the application's run cache."""
        return sha256(self.model_dump_json().encode("utf-8")).hexdigest()

    @model_validator(mode="after")
    def validate_adaptive_threshold(self) -> SimulationRunRequest:
        """Require a threshold only when adaptive mode is requested."""
        if self.strategy == AdaptiveStrategy.name:
            if self.irregularity_threshold is None:
                raise ValueError("irregularity_threshold is required for adaptive")
        elif "irregularity_threshold" in self.model_fields_set:
            raise ValueError("irregularity_threshold is only valid for adaptive")
        return self

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, value: str) -> str:
        """Require a registered strategy name before any scenario is loaded.

        The validation error lists the current registry choices for API callers.
        """
        if value not in STRATEGIES:
            choices = ", ".join(STRATEGIES.names())
            raise ValueError(f"strategy must be one of: {choices}")
        return value


class UnknownConnectionError(ValueError):
    """Signal that the requested connection is absent from the layout catalog.

    The route translates this domain lookup failure into an HTTP 404 response.
    """


class SimulationRunService:
    """Execute demo scenarios once per settings key and return detached results.

    Each application instance owns a bounded LRU cache shared by its requests.
    Scenario files and schedules remain read-only during independent runs.
    """

    def __init__(self, station_layouts: Mapping[str, StationLayoutResponse]) -> None:
        """Load fixed network data and prepare a bounded per-app result cache.

        The supplied layouts are validated at app startup. Connection lookups use
        the same index as the connection-data route, so both agree on which
        layout owns a connection; a repeated connection ID raises ValueError.
        """
        self._connections = index_connections(station_layouts)
        self._network = load_reference_network()
        self._dataset = dataset_metadata(self._network)
        self._cache: OrderedDict[str, dict[str, object]] = OrderedDict()
        self._in_flight: dict[str, Future[SimulationRunResponse]] = {}
        self._cache_lock = RLock()

    def run(self, request: SimulationRunRequest) -> SimulationRunResponse:
        """Return a cached station-view response or run the selected scenario.

        Identical requests share an in-flight future; distinct settings can run
        concurrently. Cached payloads are reconstructed into typed responses.
        Least-recently-used entries are evicted after the configured cache limit.
        """
        cache_key = request.run_id
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._cache.move_to_end(cache_key)
                log.debug("simulation cache hit: %s", request.connection_id)
                return SimulationRunResponse.model_validate(deepcopy(cached))
            future = self._in_flight.get(cache_key)
            is_owner = future is None
            if future is None:
                future = Future()
                self._in_flight[cache_key] = future

        if not is_owner:
            return deepcopy(future.result())

        try:
            response = self._run_uncached(request)
        except BaseException as error:
            with self._cache_lock:
                self._in_flight.pop(cache_key, None)
            future.set_exception(error)
            raise

        with self._cache_lock:
            self._cache[cache_key] = response.model_dump(mode="json")
            if len(self._cache) > MAX_CACHED_RUNS:
                self._cache.popitem(last=False)
            self._in_flight.pop(cache_key, None)
        future.set_result(response)
        return response

    def results(self, run_id: str) -> RunResultsResponse | None:
        """Read completed results and refresh their position in the shared LRU."""
        with self._cache_lock:
            cached = self._cache.get(run_id)
            if cached is None:
                return None
            self._cache.move_to_end(run_id)
        # Published cache entries are never mutated. Validate only result sections.
        return RunResultsResponse.model_validate(cached)

    def _run_uncached(self, request: SimulationRunRequest) -> SimulationRunResponse:
        """Run and serialize one validated settings combination.

        The event and decision logs are read before the temporary directory is
        removed.
        Simulator, filesystem, and serialization errors propagate to the route.
        A failed run never enters the response cache.
        """
        layout, connection = self._select_connection(request.connection_id)
        scenario = self._load_scenario(
            request, layout.interchange.id, connection.to_platform_id
        )
        run_state: dict[str, TransferComponent] = {}
        audit_sources: list[TrainComponent] = []

        def build_components(
            configured: Scenario, streams: object
        ) -> Sequence[Component]:
            """Retain transfer state for event-to-playback conversion after the run.

            The runner's factory contract supplies its seeded stream manager.
            """
            if not isinstance(streams, StreamManager):
                raise TypeError("simulation stream factory returned an invalid manager")
            transfers, trains = _build_components(
                configured, self._network, layout, connection, request, streams
            )
            run_state["transfers"] = transfers
            audit_sources.append(trains)
            return trains, transfers

        log.info(
            "starting API simulation: connection=%s strategy=%s flow=%s",
            request.connection_id,
            request.strategy,
            request.passenger_flow,
        )
        with tempfile.TemporaryDirectory(prefix="transitsync-api-run-") as folder:
            result = run_scenario(
                scenario, StreamManager, build_components, Path(folder)
            )
            event_records = _read_json_lines(result.events_path)
            # The audit log carries adaptive mode switches for the timeline (#60).
            decision_records = _decision_playback(
                audit_sources[0] if audit_sources else None,
                result.decisions_path,
                event_records,
                connection,
            )
            return build_station_view_response(
                layout,
                connection,
                scenario,
                event_records,
                run_state["transfers"],
                decision_records,
                run_id=request.run_id,
            )

    def starting_conditions(self, connection_id: str) -> Scenario:
        """Return the committed scenario a connection's runs start from.

        Paired comparisons show its service date, master seed and duration so
        users can see both runs share them. Raises ``UnknownConnectionError``
        for a connection missing from the catalog.
        """
        layout, _connection = self._select_connection(connection_id)
        return load_scenario_file(
            SCENARIO_PATHS[layout.interchange.id], {DATASET_ID: self._dataset}
        )

    def _select_connection(
        self, connection_id: str
    ) -> tuple[StationLayoutResponse, Connection]:
        """Resolve a public connection ID using the validated static catalog.

        Returns the containing layout and connection; raises
        ``UnknownConnectionError`` when no configured interchange matches.
        """
        data = self._connections.get(connection_id)
        if data is None:
            raise UnknownConnectionError(f"Unknown connection: {connection_id}")
        return data.station_layout, data.connection

    def _load_scenario(
        self,
        request: SimulationRunRequest,
        interchange_id: str,
        connecting_platform_id: str,
    ) -> Scenario:
        """Load the committed one-hour scenario and apply validated run settings.

        Headway regulation uses platform targets, and connection protection uses
        the selected destination's median service gap. Adaptive mode uses both.
        The maximum hold is set in both control search and operating safeguards.
        Prediction-error kappa is shared across arrival, transfer, and load inputs.
        Returned scenario state is replaced rather than mutating the committed data.
        """
        scenario = load_scenario_file(
            SCENARIO_PATHS[interchange_id], {DATASET_ID: self._dataset}
        )
        uses_targets = request.strategy in TARGET_HEADWAY_STRATEGIES
        uses_connections = request.strategy in CONNECTION_HEADWAY_STRATEGIES
        headways = (
            _headway_targets(self._network, scenario)
            if uses_targets or uses_connections
            else {}
        )
        control = replace(
            scenario.control,
            strategy=request.strategy,
            target_headways_s=headways if uses_targets else None,
            connection_headways_s=(
                {connecting_platform_id: headways[connecting_platform_id]}
                if uses_connections
                else None
            ),
            irregularity_threshold=request.irregularity_threshold,
            hold_search=replace(
                scenario.control.hold_search,
                max_hold_s=request.max_hold_time,
            ),
            prediction_error=PredictionErrorSettings(
                arrival_kappa=request.error_magnitude,
                transfer_kappa=request.error_magnitude,
                load_kappa=request.error_magnitude,
            ),
        )
        return replace(
            scenario,
            control=control,
            operating_rules=replace(
                scenario.operating_rules, max_hold_time=request.max_hold_time
            ),
        )


def _headway_targets(network: NetworkConfig, scenario: Scenario) -> dict[str, float]:
    """Use each platform's median scheduled gap, in seconds, as its target.

    Only departures inside the scenario's own window count. A whole-day median
    mixes peak and off-peak service, so a peak-hour run would aim for the wider
    off-peak gap and hold every train (300 s target against 180 s service).
    Departures are grouped by platform so the strategy receives platform keys.
    Platforms without two departures receive the conservative 300-second target.
    """
    start_s = scenario_start_clock_s(scenario)
    end_s = start_s + scenario.duration_s
    departures: dict[str, list[int]] = defaultdict(list)
    for trip in network.trips_for_date(scenario.service_date):
        for visit in trip.visits:
            in_window = start_s <= visit.departure_s < end_s
            if visit.outgoing_passenger_service and in_window:
                departures[visit.platform_id].append(visit.departure_s)
    targets = {}
    for platform in network.platforms:
        ordered = sorted(departures[platform.platform_id])
        gaps = [
            later - earlier
            for earlier, later in zip(ordered, ordered[1:], strict=False)
        ]
        targets[platform.platform_id] = statistics.median(gaps) if gaps else 300.0
    return targets


def _build_components(
    scenario: Scenario,
    network: NetworkConfig,
    layout: StationLayoutResponse,
    connection: Connection,
    request: SimulationRunRequest,
    streams: StreamManager,
) -> tuple[TransferComponent, TrainComponent]:
    """Build fresh transfer and train state for the requested run.

    Platform IDs come from the selected connection's validated layout record.
    Both components share the request's seeded stream manager.
    """
    platform_by_id = {platform.platform_id: platform for platform in layout.platforms}
    feeder = platform_by_id[connection.from_platform_id]
    connecting = platform_by_id[connection.to_platform_id]
    route = _build_transfer_route(scenario, request, feeder, connecting)
    transfers = TransferComponent([route], streams)
    trains = _build_train_component(
        scenario, network, connection, request, transfers, route, streams
    )
    return transfers, trains


def _build_transfer_route(
    scenario: Scenario,
    request: SimulationRunRequest,
    feeder: LayoutPlatform,
    connecting: LayoutPlatform,
) -> TransferRoute:
    """Configure the REM-to-metro route shared by passengers and the strategy.

    The demand profile spans the scenario horizon and uses passengers per minute.
    One destination is assigned to the selected connecting station.
    """
    return TransferRoute(
        station_id=feeder.stop_id,
        feeder_platform_id=feeder.platform_id,
        connecting_platform_id=connecting.platform_id,
        demand_profile=DemandProfile(
            (
                DemandPeriod(
                    0,
                    float(scenario.duration_s),
                    DEMAND_RATES_PER_MINUTE[request.passenger_flow],
                ),
            )
        ),
        # Transfers ride on past the interchange, so they can board (#100)
        transfer_fractions={_onward_station_id(connecting.platform_id): 1.0},
        corridor=CorridorQueue(CORRIDOR_CAPACITY_PER_MINUTE),
        walking_mean_s=WALKING_MEAN_S,
        walking_min_s=WALKING_MIN_S,
    )


def _build_train_component(
    scenario: Scenario,
    network: NetworkConfig,
    connection: Connection,
    request: SimulationRunRequest,
    transfers: TransferComponent,
    route: TransferRoute,
    streams: StreamManager,
) -> TrainComponent:
    """Build trains with a registered Strategy and configured run safeguards.

    Prediction errors use their dedicated named stream for reproducible runs.
    The platform queue and walking estimate both use the connection's metro side.
    """
    trains = _build_trains(
        network,
        scenario,
        route.connecting_platform_id,
        request,
        streams,
    )
    platform_ids = [p.platform_id for p in network.platforms]
    adaptive = scenario.control.strategy == AdaptiveStrategy.name
    if adaptive:
        validate_headway_configuration(
            scenario.control,
            trains,
            platform_ids,
            scenario.operating_rules.min_safe_gap,
        )
    if scenario.control.strategy in CONNECTION_HEADWAY_STRATEGIES:
        strategy = build_selected_connection_protection(
            scenario.control, [route], platform_ids
        )
    else:
        strategy = STRATEGIES.build(
            scenario.control.strategy,
            target_headways_s=scenario.control.target_headways_s,
            walking_by_platform={
                route.connecting_platform_id: ShiftedExponentialCdf(
                    mean_s=route.walking_mean_s, min_s=route.walking_min_s
                )
            },
            rolling_horizon=scenario.control.rolling_horizon,
            hold_search=scenario.control.hold_search,
            weights=scenario.control.weights,
        )
    # Every strategy sees the incoming transfer groups, not only adaptive:
    # connection protection and rolling horizon hold for them, and identical
    # observations keep strategy comparisons on the same random draws.
    decision = DecisionPipeline(
        strategy,
        builder=ObservationBuilder([transfers]),
        enforcer=OperatingRulesEnforcer(scenario.operating_rules),
        error_model=PredictionErrorModel(
            scenario.control.prediction_error,
            partial(streams.keyed_normal, "prediction_errors"),
        ),
    )
    return TrainComponent(
        trains,
        minimum_gap_s=scenario.operating_rules.min_safe_gap,
        delay_injections=_delay_injections(connection, request),
        suspensions=_line_suspensions(request, network, connection),
        passenger_queue=PlatformQueue(
            (route.connecting_platform_id,), passengers=transfers.passengers
        ),
        decision=decision,
        control=scenario.control,
    )


def _delay_injections(
    connection: Connection, request: SimulationRunRequest
) -> tuple[DelayInjection, ...]:
    """Build a platform delay from the legacy toggle or the preset picker.

    The legacy boolean remains accepted for older clients. It is equivalent
    to a 60-second platform delay starting at 120 seconds.
    """
    injections = []
    platform_delay = request.disruption_preset == "platform_delay" or (
        request.disruption_preset == "none" and request.disruption_enabled
    )
    if platform_delay:
        injections.append(
            DelayInjection(
                disruption_id="demo-rem-delay",
                time_s=request.disruption_time_s,
                delay_s=request.disruption_magnitude,
                platform_id=connection.from_platform_id,
            )
        )
    return tuple(injections)


def _line_suspensions(
    request: SimulationRunRequest,
    network: NetworkConfig,
    connection: Connection,
) -> tuple[LineSuspension, ...]:
    """Create a suspension for the selected metro connection route."""
    if request.disruption_preset != "line_suspension":
        return ()
    connecting_platform = next(
        (
            platform
            for platform in network.platforms
            if platform.platform_id == connection.to_platform_id
        ),
        None,
    )
    if connecting_platform is None:
        raise ValueError(f"Unknown connecting platform: {connection.to_platform_id}")
    route_ids = tuple(connecting_platform.route_ids)
    if not route_ids:
        raise ValueError(
            f"Connecting platform has no metro route: {connection.to_platform_id}"
        )
    end_s = request.disruption_time_s + request.disruption_magnitude
    return tuple(
        LineSuspension(route_id, request.disruption_time_s, end_s)
        for route_id in route_ids
    )


def _nominal_first_departure(
    active_visits: Sequence[ScheduledVisit],
    start_clock_s: float,
) -> float:
    """Return the first active visit's relative departure in seconds."""
    first_visit = active_visits[0]
    return float(_departure_with_dwell(first_visit) - start_clock_s)


def _irregular_green_starts(
    network: NetworkConfig,
    scenario: Scenario,
    start_clock_s: float,
    request: SimulationRunRequest | None,
    streams: StreamManager | None,
) -> dict[tuple[str, str], float]:
    """Perturb Green-line dispatch starts using the named preset level."""
    if request is None or request.disruption_preset != "uneven_headways":
        return {}
    preset = get_disruption_preset("uneven_headways")
    level = preset.spacing_irregularity_level
    if level is None:
        return {}
    if streams is None:
        raise ValueError("Uneven headways require a seeded disruptions stream")

    departures = []
    for trip in network.trips_for_date(scenario.service_date):
        if trip.route_id != "1":
            continue
        active_visits = [
            visit for visit in trip.visits if visit.departure_s >= start_clock_s
        ]
        if active_visits:
            nominal = _nominal_first_departure(active_visits, start_clock_s)
            departures.append(((trip.feed_id, trip.trip_id), nominal))

    ordered = sorted(departures, key=lambda item: item[1])
    nominal_starts = [nominal for _key, nominal in ordered]
    perturbed_starts = perturb_dispatch_times(
        nominal_starts,
        level,
        streams.get_stream("disruptions"),
    )
    return {
        key: perturbed
        for (key, _nominal), perturbed in zip(
            ordered,
            perturbed_starts,
            strict=True,
        )
    }


def _build_trains(
    network: NetworkConfig,
    scenario: Scenario,
    connecting_platform_id: str,
    request: SimulationRunRequest | None = None,
    streams: StreamManager | None = None,
) -> list[Train]:
    """Convert remaining timetable visits to second-based simulation trains.

    A stop remains active when its departure is at or after the scenario start.
    Scheduled timestamps are shifted to seconds relative to that start clock.
    A stop the timetable lists with no dwell gets ``MIN_STOP_DWELL_S``.
    Every train starts with ``ONBOARD_LOAD`` passengers. A trip that ends at
    the connecting platform gets an onward stop (see ``_onward_stop``).
    """
    start_clock_s = scenario_start_clock_s(scenario)
    irregular_starts = _irregular_green_starts(
        network,
        scenario,
        start_clock_s,
        request,
        streams,
    )
    trains = []
    for trip in network.trips_for_date(scenario.service_date):
        active_visits = [
            visit for visit in trip.visits if visit.departure_s >= start_clock_s
        ]
        if not active_visits:
            continue
        stops = tuple(
            ScheduledStop(
                station_id=visit.stop_id,
                platform_id=visit.platform_id,
                arrival_s=max(0.0, visit.arrival_s - start_clock_s),
                departure_s=_departure_with_dwell(visit) - start_clock_s,
            )
            for visit in active_visits
        )
        if stops[-1].platform_id == connecting_platform_id:
            stops = (*stops, _onward_stop(stops[-1], scenario.duration_s))
        trip_key = (trip.feed_id, trip.trip_id)
        if trip.route_id == "1" and trip_key in irregular_starts:
            nominal_start = _nominal_first_departure(
                active_visits,
                start_clock_s,
            )
            offset = irregular_starts[trip_key] - nominal_start
            stops = tuple(
                replace(
                    stop,
                    arrival_s=max(0.0, stop.arrival_s + offset),
                    departure_s=max(0.0, stop.departure_s + offset),
                )
                for stop in stops
            )
        trains.append(
            Train(
                id=f"{trip.feed_id}:{trip.trip_id}",
                capacity=TRAIN_CAPACITY,
                schedule=stops,
                line_id=trip.route_id,
                onboard_load=ONBOARD_LOAD,
            )
        )
    return trains


def _onward_station_id(platform_id: str) -> str:
    """Name the unmodelled rest of the line beyond a connecting platform."""
    return f"{platform_id}-onward"


def _onward_stop(last: ScheduledStop, duration_s: float) -> ScheduledStop:
    """Stand for the rest of the connecting line, which is not modelled.

    The reference network has only the interchange stops, so a metro trip has
    no later stop and passengers could never board it: boarding needs the
    passenger's destination among the train's later stops. Transfers ride to
    this stop instead. It reuses the platform, which every strategy already
    knows, and is reached one whole run after leaving, so it never happens
    during the run: no extra arrivals, decisions or alightings.
    """
    arrival_s = last.departure_s + duration_s
    return ScheduledStop(
        station_id=_onward_station_id(last.platform_id),
        platform_id=last.platform_id,
        arrival_s=arrival_s,
        departure_s=arrival_s,
    )


def _departure_with_dwell(visit: ScheduledVisit) -> float:
    """Return the timetable departure, moved later only for a zero-dwell stop."""
    if visit.departure_s == visit.arrival_s:
        return visit.arrival_s + MIN_STOP_DWELL_S
    return visit.departure_s


def _decision_playback(source, path, events, connection):
    """Reuse compact views from a successful run; retain file-backed fallback.

    The runner has already encoded and written the complete audit before this
    path is used. Full records remain available to public readers and on disk.
    Alternative runners without retained components still validate the log.
    """
    records = getattr(source, "playback_decision_records", None)
    if records is None:
        yield from _playback_audit_lines(path, events, connection)
        return
    for record in records():
        if isinstance(record, EncodedDecisionRecord):
            yield _decode_log_record(record.decision_line or record.line)
        else:
            yield record


def _read_json_lines(path: Path) -> list[dict[str, object]]:
    """Parse an internal event log into its ordered records.

    File and JSON decoding errors propagate to the API's logged failure handler.
    """
    return list(_iter_json_lines(path))


def _iter_json_lines(path: Path):
    """Read one complete record at a time, avoiding a second full-log string."""
    with path.open(encoding="utf-8") as file:
        for line in file:
            yield _decode_log_record(line)


def _decode_log_record(line: str):
    """Reuse the native decoder while retaining stdlib inputs and decode errors."""
    try:
        return from_json(line)
    except ValueError:
        return json.loads(line)


class _AuditHeader(BaseModel):
    """Validate whole-record JSON without allocating unused train dictionaries.

    Keep metadata as-is, matching dict.get in the existing playback adapter.
    Ignoring extra fields saves Python allocations, not JSON syntax checks.
    """

    model_config = ConfigDict(extra="ignore")
    kind: Any = None
    time_s: Any = None
    train_id: Any = None
    platform_id: Any = None


def _playback_audit_lines(path: Path, events, connection: Connection):
    """Decode estimate bodies only for holds actually shown by the adapter.

    The full audit is still written unchanged. Every line's JSON is validated;
    mode switches and other audit kinds retain their existing reader path.
    Unsupported legacy JSON falls back to the original decoder, including its
    corruption errors. No passenger or movement record is filtered here.
    """
    platforms = {connection.from_platform_id, connection.to_platform_id}
    needed = {
        (event["time_s"], event["train_id"], event["platform_id"])
        for event in events
        if event.get("event_type") == EventType.HOLD.value
        and event.get("platform_id") in platforms
    }
    with path.open(encoding="utf-8") as file:
        for line in file:
            try:
                header = _AuditHeader.model_validate_json(line)
            except ValueError:
                yield json.loads(line)
                continue
            key = (header.time_s, header.train_id, header.platform_id)
            if header.kind != KIND_ESTIMATES or key in needed:
                yield _decode_log_record(line)
