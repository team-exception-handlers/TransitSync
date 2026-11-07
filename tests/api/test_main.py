"""Tests for the FastAPI endpoints and environment configuration."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api import station_layout
from api.main import create_app

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_health_endpoint_returns_typed_response_and_default_cors_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check health payload and default development-server CORS access.

    This verifies the default configuration as well as endpoint behavior.
    CORS remains restricted to the configured development origin.
    Health stays available independently of station-layout selection.
    """
    monkeypatch.delenv("TRANSITSYNC_CORS_ORIGINS", raising=False)
    client = TestClient(create_app())

    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_station_layout_endpoint_serves_map_platforms_and_transfer_edges() -> None:
    """Serve the front-end's McGill coordinates with joined platform metadata.

    The geometry must stay compatible with the map fixture currently in use.
    Both its station and transfer paths are part of the drawing contract.
    """
    client = TestClient(create_app())

    response = client.get("/station-layout/mcgill")
    mock_layout = json.loads(
        (REPOSITORY_ROOT / "web/src/data/mock-interchange.json").read_text(
            encoding="utf-8"
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["interchange"]["id"] == "mcgill"
    assert payload["interchange"] == mock_layout["interchange"]
    assert payload["map"] == mock_layout["map"]
    assert payload["stations"] == mock_layout["stations"]
    assert len(payload["platforms"]) == 4
    assert payload["platforms"][0]["position"] == {"x": 230.0, "y": 135.0}
    assert payload["corridors"][0]["path"] == mock_layout["corridors"][0]["path"]
    assert payload["connections"] == mock_layout["connections"]


@pytest.mark.parametrize(
    ("interchange_id", "metro_line", "interchange_label"),
    [
        (
            "gare_centrale_bonaventure",
            "orange",
            "Gare Centrale ↔ Bonaventure",
        ),
        ("edouard_montpetit", "blue", "Édouard-Montpetit"),
    ],
)
def test_station_layout_endpoint_remaps_platforms_for_other_interchanges(
    interchange_id: str, metro_line: str, interchange_label: str
) -> None:
    """Reuse the map geometry while keeping selected interchange identities.

    Both non-template Metro lines must keep their own directional platform IDs.
    Catalog order keeps REM platforms first for the existing map renderer.
    The source geometry intentionally reuses positions across all three IDs.
    """
    client = TestClient(create_app())

    response = client.get(f"/station-layout/{interchange_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["interchange"]["id"] == interchange_id
    assert payload["interchange"]["name"] == interchange_label
    assert payload["connections"][0]["label"] == interchange_label
    assert payload["platforms"][0]["platform_id"] == f"rem_{interchange_id}_0"
    assert payload["connections"][0]["id"] == f"{interchange_id}-rem-{metro_line}"
    assert payload["connections"][0]["from_platform_id"] == f"rem_{interchange_id}_0"
    assert payload["connections"][0]["corridor_id"] == (
        f"{interchange_id}_rem_{metro_line}_transfer"
    )


def test_station_layout_endpoint_rejects_unknown_interchange() -> None:
    """Return a not-found response rather than silently selecting a layout.

    Unknown names must not fall back to the McGill template.
    The response identifies the unsupported interchange ID.
    """
    client = TestClient(create_app())

    response = client.get("/station-layout/unknown")

    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown interchange: unknown"}


def test_catalog_identifies_placeholder_layouts_and_replacement_location() -> None:
    """Keep future real-layout work visible in the source catalog."""
    catalog = json.loads(
        (REPOSITORY_ROOT / "config/station_layouts.json").read_text(encoding="utf-8")
    )
    notes = " ".join(catalog["maintainer_notes"])

    assert "gare_centrale_bonaventure" in notes
    assert "edouard_montpetit" in notes
    assert "Replace their layouts in this file" in notes


def test_station_layout_startup_rejects_missing_reference_interchange(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Fail app startup when a supported interchange has no catalog entry.

    The route should not hide a broken static catalog behind a later 404.
    """
    catalog = json.loads(station_layout.LAYOUT_PATH.read_text(encoding="utf-8"))
    del catalog["layouts"]["edouard_montpetit"]
    catalog_path = tmp_path / "station_layouts.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setattr(station_layout, "LAYOUT_PATH", catalog_path)

    with pytest.raises(ValueError, match="missing=.*edouard_montpetit"):
        create_app()


def test_station_layout_startup_rejects_connection_corridor_endpoint_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reject an existing but inconsistent platform endpoint at startup.

    The connection endpoints must describe the same map path as its corridor.
    """
    catalog = json.loads(station_layout.LAYOUT_PATH.read_text(encoding="utf-8"))
    connection = catalog["layouts"]["mcgill"]["connections"][0]
    connection["to_platform_id"] = "green_mcgill_1"
    catalog_path = tmp_path / "station_layouts.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setattr(station_layout, "LAYOUT_PATH", catalog_path)

    with pytest.raises(ValueError, match="endpoints do not match corridor"):
        create_app()


@pytest.mark.parametrize(
    "interchange_id",
    [
        "gare_centrale_bonaventure",
        "mcgill",
        "edouard_montpetit",
    ],
)
def test_station_layout_platforms_match_the_saved_mapping(
    interchange_id: str,
) -> None:
    """Keep response metadata aligned with the canonical reference network.

    Feed identity and directional details are joined from network.json rather
    than duplicated in station_layouts.json.
    Comparing every canonical field protects the complete response contract.
    Each interchange must retain all its mapped platforms.
    Catalog assertions prevent metadata from being copied into geometry.
    """
    client = TestClient(create_app())
    network = json.loads(
        (REPOSITORY_ROOT / "config/reference_network/network.json").read_text(
            encoding="utf-8"
        )
    )
    layout_catalog = json.loads(
        (REPOSITORY_ROOT / "config/station_layouts.json").read_text(encoding="utf-8")
    )

    response = client.get(f"/station-layout/{interchange_id}")

    assert response.status_code == 200
    expected = {
        platform["platform_id"]: platform
        for schedule in network["schedules"]
        for platform in schedule["platforms"]
        if platform["interchange_id"] == interchange_id
    }
    actual = {
        platform["platform_id"]: platform for platform in response.json()["platforms"]
    }
    assert set(actual) == set(expected)
    geometry = layout_catalog["layouts"][interchange_id]
    assert "platforms" not in geometry
    assert set(geometry["platform_layouts"]) == set(expected)
    assert all(
        set(item) == {"station_id", "position"}
        for item in geometry["platform_layouts"].values()
    )
    assert all(
        set(station) == {"id", "name", "position"} for station in geometry["stations"]
    )
    for platform_id, platform in expected.items():
        assert actual[platform_id]["source_feed_id"] == platform["feed_id"]
        assert actual[platform_id]["interchange_id"] == interchange_id
        assert actual[platform_id]["line_id"] == platform["line_id"]
        assert actual[platform_id]["direction_id"] == platform["direction_id"]
        assert actual[platform_id]["direction_label"] == platform["direction_label"]
        assert actual[platform_id]["stop_id"] == platform["stop_id"]
        assert actual[platform_id]["stop_name"] == platform["stop_name"]
        assert actual[platform_id]["route_ids"] == platform["route_ids"]


def test_cors_uses_comma_separated_origins_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check configured origins are split, trimmed, and allowed.

    The request uses the second origin to verify parsing of multiple values.
    Only configured origins are reflected in the browser response.
    This protects the comma-separated environment setting contract.
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
    Browser access still requires an explicitly allowed origin.
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
    This protects the API's narrow cross-origin request contract.
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
    These failures must remain explicit rather than allowing all HTTP methods.
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
    Invalid process settings must not create a partially configured app.
    """
    monkeypatch.setenv("TRANSITSYNC_CORS_ORIGINS", origins)

    with pytest.raises(ValidationError, match="cors_origins"):
        create_app()
