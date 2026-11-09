# AI contribution: 50% or more AI-generated
"""Run committed demo scenarios and cache their map-ready API responses.

The API selects scenario files by connection ID, applies validated request
settings, then delegates event processing to the simulator. Simulation time
and every hold duration are expressed in seconds.
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
from datetime import date
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.network_data import DATASET_ID, dataset_metadata, load_reference_network
from api.station_layout import Connection, StationLayoutResponse
from api.station_layout import Platform as LayoutPlatform
from api.station_view import SimulationRunResponse, build_station_view_response
from api.time_utils import scenario_start_clock_s
from simulator.control.connection_configuration import (
    build_selected_connection_protection,
)
from simulator.control.decision import DecisionPipeline
from simulator.control.prediction_error import (
    PredictionErrorModel,
    PredictionErrorSettings,
)
from simulator.control.rules import OperatingRulesEnforcer
from simulator.control.strategies import STRATEGIES
from simulator.control.walking_cdf import ShiftedExponentialCdf
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
from simulator.trains.disruption import DelayInjection
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

        The supplied layouts are validated at app startup and reused for lookups.
        """
        self._station_layouts = station_layouts
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
        cache_key = request.model_dump_json()
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

    def _run_uncached(self, request: SimulationRunRequest) -> SimulationRunResponse:
        """Run and serialize one validated settings combination.

        The event log is consumed before its temporary directory is removed.
        Simulator, filesystem, and serialization errors propagate to the route.
        A failed run never enters the response cache.
        """
        layout, connection = self._select_connection(request.connection_id)
        scenario = self._load_scenario(
            request, layout.interchange.id, connection.to_platform_id
        )
        run_state: dict[str, TransferComponent] = {}

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
            return build_station_view_response(
                layout, connection, scenario, event_records, run_state["transfers"]
            )

    def _select_connection(
        self, connection_id: str
    ) -> tuple[StationLayoutResponse, Connection]:
        """Resolve a public connection ID using the validated static catalog.

        Returns the containing layout and connection; raises
        ``UnknownConnectionError`` when no configured interchange matches.
        """
        for layout in self._station_layouts.values():
            for connection in layout.connections:
                if connection.id == connection_id:
                    return layout, connection
        raise UnknownConnectionError(f"Unknown connection: {connection_id}")

    def _load_scenario(
        self,
        request: SimulationRunRequest,
        interchange_id: str,
        connecting_platform_id: str,
    ) -> Scenario:
        """Load the committed one-hour scenario and apply validated run settings.

        Headway targets are derived only for the headway-regulation strategy.
        Connection protection uses the selected destination's median service gap.
        The maximum hold is set in both control search and operating safeguards.
        Prediction-error kappa is shared across arrival, transfer, and load inputs.
        Returned scenario state is replaced rather than mutating the committed data.
        """
        scenario = load_scenario_file(
            SCENARIO_PATHS[interchange_id], {DATASET_ID: self._dataset}
        )
        headways = (
            _headway_targets(self._network, scenario.service_date)
            if request.strategy in {"headway_regulation", "connection_protection"}
            else {}
        )
        control = replace(
            scenario.control,
            strategy=request.strategy,
            target_headways_s=(
                headways if request.strategy == "headway_regulation" else None
            ),
            connection_headways_s=(
                {connecting_platform_id: headways[connecting_platform_id]}
                if request.strategy == "connection_protection"
                else None
            ),
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


def _headway_targets(network: NetworkConfig, service_date: date) -> dict[str, float]:
    """Use each platform's median scheduled gap, in seconds, as its target.

    Departures are grouped by platform so the strategy receives platform keys.
    Platforms without two departures receive the conservative 300-second target.
    """
    departures: dict[str, list[int]] = defaultdict(list)
    for trip in network.trips_for_date(service_date):
        for visit in trip.visits:
            if visit.outgoing_passenger_service:
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
        transfer_fractions={f"{connecting.stop_id}-destination": 1.0},
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
    trains = _build_trains(network, scenario)
    if scenario.control.strategy == "connection_protection":
        # Validate coverage and derive walking CDFs from the passenger route.
        strategy = build_selected_connection_protection(
            scenario.control, [route], [p.platform_id for p in network.platforms]
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
    decision = DecisionPipeline(
        strategy,
        enforcer=OperatingRulesEnforcer(scenario.operating_rules),
        error_model=PredictionErrorModel(
            scenario.control.prediction_error,
            streams.get_stream("prediction_errors"),
        ),
    )
    return TrainComponent(
        trains,
        minimum_gap_s=scenario.operating_rules.min_safe_gap,
        delay_injections=_delay_injections(connection, request),
        passenger_queue=PlatformQueue(
            (route.connecting_platform_id,), passengers=transfers.passengers
        ),
        decision=decision,
        control=scenario.control,
    )


def _delay_injections(
    connection: Connection, request: SimulationRunRequest
) -> tuple[DelayInjection, ...]:
    """Apply the demo's 60-second delay to the selected REM feeder if enabled.

    The injection is scheduled at 120 seconds of relative simulation time.
    """
    if not request.disruption_enabled:
        return ()
    return (
        DelayInjection(
            disruption_id="demo-rem-delay",
            time_s=120,
            delay_s=60,
            platform_id=connection.from_platform_id,
        ),
    )


def _build_trains(network: NetworkConfig, scenario: Scenario) -> list[Train]:
    """Convert remaining timetable visits to second-based simulation trains.

    A stop remains active when its departure is at or after the scenario start.
    Scheduled timestamps are shifted to seconds relative to that start clock.
    """
    start_clock_s = scenario_start_clock_s(scenario)
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
                departure_s=visit.departure_s - start_clock_s,
            )
            for visit in active_visits
        )
        trains.append(
            Train(
                id=f"{trip.feed_id}:{trip.trip_id}",
                capacity=TRAIN_CAPACITY,
                schedule=stops,
                line_id=trip.route_id,
            )
        )
    return trains


def _read_json_lines(path: Path) -> list[dict[str, object]]:
    """Parse an internal event log into its ordered records.

    File and JSON decoding errors propagate to the API's logged failure handler.
    """
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
