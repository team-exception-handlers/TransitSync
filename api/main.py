"""FastAPI application and health endpoint."""

from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.settings import Settings


class HealthResponse(BaseModel):
    """Typed successful health-check response whose status is always ``ok``."""

    status: Literal["ok"]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API with explicit or validated process-environment settings.

    Invalid environment configuration raises Pydantic's ``ValidationError``.
    """
    app_settings = settings if settings is not None else Settings.from_environment()
    application = FastAPI(title="TransitSync API")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/health", response_model=HealthResponse, tags=["health"])
    def health_check() -> HealthResponse:
        """Return the typed response indicating that the API is available."""
        return HealthResponse(status="ok")

    return application


app = create_app()
