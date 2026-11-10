# AI contribution: 50% or more AI-generated
"""Tests for retrieving station data by connection ID (#78).

The expected platform IDs are written out by hand rather than read from the
catalog, so a wrong join between connections and layouts cannot pass by
comparing the catalog with itself. Requests go through the real app and the
committed config, so these also check the route, the lookup and the catalog
together.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import station_layout
from api.connection_data import index_connections
from api.main import create_app


@pytest.mark.parametrize(
    ("connection_id", "interchange_id", "metro_line", "from_platform", "to_platform"),
    [
        (
            "gare_centrale_bonaventure-rem-orange",
            "gare_centrale_bonaventure",
            "orange",
            "rem_gare_centrale_bonaventure_0",
            "orange_gare_centrale_bonaventure_0",
        ),
        (
            "mcgill-rem-green",
            "mcgill",
            "green",
            "rem_mcgill_0",
            "green_mcgill_0",
        ),
        (
            "edouard_montpetit-rem-blue",
            "edouard_montpetit",
            "blue",
            "rem_edouard_montpetit_0",
            "blue_edouard_montpetit_0",
        ),
    ],
)
def test_connection_endpoint_serves_station_and_platforms_for_named_connection(
    connection_id: str,
    interchange_id: str,
    metro_line: str,
    from_platform: str,
    to_platform: str,
) -> None:
    """Each of the three connections resolves to its own interchange and line.

    All three reuse the same placeholder map coordinates, so the checks use IDs:
    comparing positions could not tell the stations apart.
    """
    client = TestClient(create_app())

    response = client.get(f"/connections/{connection_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["connection"]["id"] == connection_id
    assert payload["connection"]["from_platform_id"] == from_platform
    assert payload["connection"]["to_platform_id"] == to_platform
    assert payload["station_layout"]["interchange"]["id"] == interchange_id
    # Two lines with two directions each: train events need all four platforms,
    # not only the two the connection joins.
    assert len(payload["station_layout"]["platforms"]) == 4
    assert {item["line_id"] for item in payload["station_layout"]["platforms"]} == {
        "rem",
        metro_line,
    }


def test_connection_endpoint_layout_matches_station_layout_endpoint() -> None:
    """Both routes return the same map, so the two views cannot drift apart."""
    client = TestClient(create_app())

    by_connection = client.get("/connections/mcgill-rem-green").json()
    by_interchange = client.get("/station-layout/mcgill").json()

    assert by_connection["station_layout"] == by_interchange


@pytest.mark.parametrize(
    "connection_id",
    [
        "unknown",
        # An interchange ID is not a connection ID, and matching is exact.
        "mcgill",
        "MCGILL-REM-GREEN",
    ],
)
def test_connection_endpoint_rejects_unknown_connection(connection_id: str) -> None:
    """Return an error naming the ID rather than falling back to another station."""
    client = TestClient(create_app())

    response = client.get(f"/connections/{connection_id}")

    assert response.status_code == 404
    assert response.json() == {"detail": f"Unknown connection: {connection_id}"}


def test_startup_rejects_connection_id_used_by_two_interchanges(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Fail at startup instead of serving one of the stations by accident.

    Each layout is valid on its own, so only the check across interchanges in
    ``index_connections`` can catch this repeated ID.
    """
    catalog = json.loads(station_layout.LAYOUT_PATH.read_text(encoding="utf-8"))
    connection = catalog["layouts"]["edouard_montpetit"]["connections"][0]
    connection["id"] = "mcgill-rem-green"
    catalog_path = tmp_path / "station_layouts.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setattr(station_layout, "LAYOUT_PATH", catalog_path)

    with pytest.raises(ValueError, match="duplicate connection ID: 'mcgill-rem-green'"):
        create_app()


def test_index_connections_maps_each_connection_in_a_layout_to_that_layout() -> None:
    """A second connection at one interchange gets its own entry and same map.

    The committed catalog has one connection per interchange, so this alternate
    path needs a layout built in the test.
    """
    layout = station_layout.load_station_layouts()["mcgill"]
    first = layout.connections[0]
    second = first.model_copy(update={"id": "mcgill-second"})
    two_connections = layout.model_copy(update={"connections": [first, second]})

    index = index_connections({"mcgill": two_connections})

    assert set(index) == {"mcgill-rem-green", "mcgill-second"}
    assert index["mcgill-second"].connection == second
    assert index["mcgill-rem-green"].connection == first
    assert index["mcgill-second"].station_layout == two_connections
