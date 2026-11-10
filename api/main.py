# AI contribution: 50% or more AI-generated
"""FastAPI application with health, station-layout, connection and simulation-run
endpoints.
"""

import logging
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.connection_data import ConnectionDataResponse, index_connections
from api.settings import Settings
from api.simulation_run import (
    SimulationRunRequest,
    SimulationRunService,
    UnknownConnectionError,
)
from api.station_layout import StationLayoutResponse, load_station_layouts
from api.station_view import SimulationRunResponse
from simulator.engine.runner import RunError

log = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    """Typed successful health-check response whose status is always ``ok``."""

    status: Literal["ok"]


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

    return application


app = create_app()
