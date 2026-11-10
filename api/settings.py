"""Environment-backed settings for the FastAPI application."""

import os
from urllib.parse import urlsplit

from pydantic import BaseModel, field_validator

DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)


class Settings(BaseModel):
    """Validated API settings, including allowed browser origins."""

    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS

    @classmethod
    def from_environment(cls) -> "Settings":
        """Load process origins, defaulting to Vite.

        Invalid values raise Pydantic's ``ValidationError``.
        """
        configured_origins = os.environ.get("TRANSITSYNC_CORS_ORIGINS")
        if configured_origins is None:
            return cls()

        origins = tuple(origin.strip() for origin in configured_origins.split(","))
        return cls(cors_origins=origins)

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, origins: tuple[str, ...]) -> tuple[str, ...]:
        """Validate exact HTTP(S) origins without paths.

        Args:
            origins: Configured browser origins.

        Returns the unchanged origins; raises ``ValueError`` for malformed input.
        """
        if not origins:
            raise ValueError("at least one CORS origin is required")

        for origin in origins:
            try:
                parsed_origin = urlsplit(origin)
                port = parsed_origin.port
            except ValueError as exc:
                raise ValueError(f"invalid CORS origin: {origin!r}") from exc

            if (
                not origin
                or parsed_origin.scheme not in {"http", "https"}
                or not parsed_origin.hostname
                or parsed_origin.username is not None
                or parsed_origin.password is not None
                or parsed_origin.path
                or parsed_origin.query
                or parsed_origin.fragment
                or (port is not None and not 1 <= port <= 65535)
            ):
                raise ValueError(
                    "CORS origins must be HTTP(S) origins without paths, "
                    f"credentials, queries, or fragments: {origin!r}"
                )

        return origins
