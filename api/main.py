# AI contribution: 50% or more AI-generated
"""FastAPI application with health, station-layout, connection and simulation-run
endpoints.
"""

import logging
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from api.connection_data import (
    ConnectionDataResponse,
    ConnectionSummary,
    index_connections,
    list_connections,
)
from api.passenger_outcomes import PassengerComparison
from api.run_results import RunResultsResponse
from api.scenario_presets import ScenarioPreset, list_presets
from api.settings import Settings
from api.simulation_comparison import (
    NO_HOLDING_STRATEGY,
    SimulationComparisonResponse,
    no_holding_request,
    run_comparison,
)
from api.simulation_run import (
    SimulationRunRequest,
    SimulationRunService,
    UnknownConnectionError,
)
from api.station_layout import StationLayoutResponse, load_station_layouts
from api.station_view import RunId, SimulationRunResponse
from simulator.engine.runner import RunError
from simulator.parameter_provenance import load_parameter_provenance

log = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    """Typed successful health-check response whose status is always ``ok``."""

    status: Literal["ok"]


def _cached_results(service: SimulationRunService, run_id: str) -> RunResultsResponse:
    """Translate missing or unreadable result sections to API errors."""
    try:
        results = service.results(run_id)
    except ValidationError as error:
        log.exception("Invalid cached results for run %s", run_id)
        raise HTTPException(500, "Cached run results are invalid") from error
    if results is None:
        raise HTTPException(404, "Run is not in the cache")
    return results


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API with explicit or validated process-environment settings.

    Invalid environment configuration raises Pydantic's ``ValidationError``.
    Committed station geometry is validated before the app accepts requests.
    Simulation results and their bounded cache are scoped to this app instance.
    """
    app_settings = settings if settings is not None else Settings.from_environment()
    application = FastAPI(title="TransitSync API")
    # Parse static map data once so requests never observe a partial layout.
    station_layouts = load_station_layouts()
    # A connection ID repeated across interchanges stops startup here, so a
    # request can never return the wrong station.
    connections = index_connections(station_layouts)
    simulation_runs = SimulationRunService(station_layouts)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @application.get("/health", response_model=HealthResponse, tags=["health"])
    def health_check() -> HealthResponse:
        """Return the typed response indicating that the API is available."""
        return HealthResponse(status="ok")

    @application.get(
        "/station-layout/{interchange_id}",
        response_model=StationLayoutResponse,
        tags=["station layout"],
    )
    def station_layout(interchange_id: str) -> StationLayoutResponse:
        """Return map-ready platforms and transfer geometry for one interchange.

        Unknown IDs return HTTP 404 rather than falling back to another layout.
        """
        layout = station_layouts.get(interchange_id)
        if layout is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown interchange: {interchange_id}",
            )
        return layout

    @application.get(
        "/connections",
        response_model=list[ConnectionSummary],
        tags=["connections"],
    )
    def connections_list() -> list[ConnectionSummary]:
        """Return every selectable connection with its metro line and interchange.

        Built from the same validated layout catalog `connection_data` serves,
        so the list and each connection's detail can never disagree (#76).
        """
        return list_connections(connections)

    @application.get(
        "/connections/{connection_id}",
        response_model=ConnectionDataResponse,
        tags=["connections"],
    )
    def connection_data(connection_id: str) -> ConnectionDataResponse:
        """Return one connection with its interchange's stations and platforms."""
        data = connections.get(connection_id)
        if data is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown connection: {connection_id}",
            )
        return data

    _add_simulation_routes(application, simulation_runs)

    @application.get(
        "/scenario/presets",
        response_model=list[ScenarioPreset],
        tags=["scenario"],
    )
    def scenario_presets() -> list[ScenarioPreset]:
        """Return the time-of-day presets and the conditions each one sets."""
        return list_presets()

    @application.get("/parameters", tags=["parameters"])
    def get_parameters():
        """Return classification and source metadata for all simulation parameters."""
        return load_parameter_provenance()

    return application


def _add_simulation_routes(
    application: FastAPI, simulation_runs: SimulationRunService
) -> None:
    """Register the routes that run simulations through the shared run cache.

    Kept apart from ``create_app`` so that function stays under the complexity
    limit. Every route here maps an unknown connection to 404 and a simulator,
    file or value failure to a logged 500.
    """

    @application.post(
        "/simulation/run",
        response_model=SimulationRunResponse,
        tags=["simulation"],
    )
    def run_simulation(settings: SimulationRunRequest) -> SimulationRunResponse:
        """Run one demo scenario and return map-ready playback data.

        Invalid settings return 422; missing connections return 404.
        """
        try:
            return simulation_runs.run(settings)
        except UnknownConnectionError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (OSError, RunError, ValueError) as error:
            log.exception(
                "simulation run failed for connection %s", settings.connection_id
            )
            raise HTTPException(
                status_code=500, detail="Simulation run failed"
            ) from error

    @application.get(
        "/simulation/runs/{run_id}/results",
        tags=["simulation"],
        responses={
            404: {"description": "Run is unknown or has been evicted"},
            500: {"description": "Cached run results are incomplete or invalid"},
        },
    )
    def run_results(run_id: RunId) -> RunResultsResponse:
        """Read statistics and chart data using the ID returned by POST /simulation/run.

        Unknown or evicted runs return 404. Malformed identifiers return 422.
        """
        return _cached_results(simulation_runs, run_id)

    @application.post("/simulation/passenger-comparison", tags=["simulation"])
    def compare_passengers(settings: SimulationRunRequest) -> PassengerComparison:
        """Return cached outcomes for matched settings with and without control."""
        # Same baseline builder as /simulation/comparison, so both endpoints
        # pair runs the same way and share one cached no-control run.
        baseline = run_simulation(no_holding_request(settings)).passenger_outcomes
        selected = baseline
        if settings.strategy != NO_HOLDING_STRATEGY:
            selected = run_simulation(settings).passenger_outcomes
        return PassengerComparison(without_holding=baseline, selected_strategy=selected)

    @application.post(
        "/simulation/comparison",
        tags=["simulation"],
        responses={
            404: {"description": "Unknown connection"},
            500: {"description": "Simulation comparison failed"},
        },
    )
    def compare_runs(settings: SimulationRunRequest) -> SimulationComparisonResponse:
        """Run the same connection with and without holding (US-4.1).

        Both runs share the scenario's date and seed. Invalid settings return
        422, unknown connections 404 and simulator failures 500.
        """
        try:
            return run_comparison(simulation_runs, settings)
        except UnknownConnectionError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (OSError, RunError, ValueError) as error:
            log.exception(
                "simulation comparison failed for connection %s",
                settings.connection_id,
            )
            raise HTTPException(
                status_code=500, detail="Simulation comparison failed"
            ) from error


app = create_app()
