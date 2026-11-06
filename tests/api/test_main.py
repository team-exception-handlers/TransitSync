"""Tests for the FastAPI health check and environment configuration."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.main import create_app


def test_health_endpoint_returns_typed_response_and_default_cors_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check health payload and default development-server CORS access.

    This verifies the default configuration as well as endpoint behavior.
    """
    monkeypatch.delenv("TRANSITSYNC_CORS_ORIGINS", raising=False)
    client = TestClient(create_app())

    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_uses_comma_separated_origins_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check configured origins are split, trimmed, and allowed.

    The request uses the second origin to verify parsing of multiple values.
    """
    monkeypatch.setenv(
        "TRANSITSYNC_CORS_ORIGINS",
        "http://localhost:3000, https://frontend.example.test",
    )
    client = TestClient(create_app())

    response = client.get(
        "/health", headers={"Origin": "https://frontend.example.test"}
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "https://frontend.example.test"
    )


def test_cors_does_not_allow_unconfigured_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check a request from an origin outside the allowlist gets no CORS grant.

    The health endpoint remains available to non-browser callers.
    """
    monkeypatch.setenv("TRANSITSYNC_CORS_ORIGINS", "http://localhost:5173")
    client = TestClient(create_app())

    response = client.get("/health", headers={"Origin": "https://untrusted.test"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_allows_get_preflight_with_content_type_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Allow the current GET API and its required content-type header.

    Browsers preflight this header, so check the method and header allowlists.
    """
    monkeypatch.setenv("TRANSITSYNC_CORS_ORIGINS", "http://localhost:5173")
    client = TestClient(create_app())

    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-methods"] == "GET"
    assert "content-type" in response.headers["access-control-allow-headers"].lower()


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_cors_rejects_unconfigured_preflight_methods(
    monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    """Reject preflights for methods not currently exposed by the API.

    A failed preflight prevents browsers from issuing that cross-origin method.
    """
    monkeypatch.setenv("TRANSITSYNC_CORS_ORIGINS", "http://localhost:5173")
    client = TestClient(create_app())

    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": method,
        },
    )

    assert response.status_code == 400
    assert response.text == "Disallowed CORS method"


def test_cors_rejects_unconfigured_preflight_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject headers outside Content-Type, such as a custom client header.

    Arbitrary request headers must not become allowed through the CORS policy.
    """
    monkeypatch.setenv("TRANSITSYNC_CORS_ORIGINS", "http://localhost:5173")
    client = TestClient(create_app())

    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )

    assert response.status_code == 400
    assert response.text == "Disallowed CORS headers"


@pytest.mark.parametrize(
    "origins",
    [
        "",
        "ftp://localhost:5173",
        "http://localhost:5173/api",
        "http://localhost:invalid",
    ],
)
def test_invalid_cors_origins_are_rejected(
    monkeypatch: pytest.MonkeyPatch, origins: str
) -> None:
    """Reject empty, non-HTTP, path-bearing, or malformed-port values.

    Bad configuration fails app creation instead of silently weakening CORS.
    """
    monkeypatch.setenv("TRANSITSYNC_CORS_ORIGINS", origins)

    with pytest.raises(ValidationError, match="cors_origins"):
        create_app()
