"""FastAPI application with health and station-layout endpoints."""

from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.settings import Settings
from api.station_layout import StationLayoutResponse, load_station_layouts


class HealthResponse(BaseModel):
    """Typed successful health-check response whose status is always ``ok``."""

    status: Literal["ok"]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API with explicit or validated process-environment settings.

    Invalid environment configuration raises Pydantic's ``ValidationError``.
    Committed station geometry is validated before the app accepts requests.
    """
    app_settings = settings if settings is not None else Settings.from_environment()
    application = FastAPI(title="TransitSync API")
    # Parse static map data once so requests never observe a partial layout.
    station_layouts = load_station_layouts()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_methods=["GET"],
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
        """Return map-ready platforms and transfer geometry for one interchange."""
        layout = station_layouts.get(interchange_id)
        if layout is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown interchange: {interchange_id}",
            )
        return layout

    return application


app = create_app()
