"""FastAPI application with health, station-layout and simulation-run endpoints."""

import logging
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
            return SimulationRunResponse.model_validate(simulation_runs.run(settings))
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
