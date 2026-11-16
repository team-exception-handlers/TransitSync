# AI contribution: 50% or more AI-generated
"""Look up the station data that belongs to one selectable connection (#78).

The front end selects connections such as ``mcgill-rem-green``, while the layout
catalog is keyed by interchange. This module joins the two with a lookup table
built once at startup, so requests never search or parse the catalog.
"""

from collections.abc import Mapping

from api.station_layout import (
    Connection,
    Interchange,
    NonEmptyText,
    StationLayoutResponse,
    StrictModel,
)


class ConnectionDataResponse(StrictModel):
    """One connection and the map data for the interchange that contains it.

    The whole layout is returned rather than only the connection's two
    platforms: train events use every directional platform at the interchange,
    so a run could not be drawn from the connection's endpoints alone.
    """

    connection: Connection
    station_layout: StationLayoutResponse


class ConnectionSummary(StrictModel):
    """One selectable connection's identity, metro line, and interchange (#76).

    This is the catalog-listing view: enough for the station-connection
    selector to render every choice without the interchange's full map data.
    """

    id: NonEmptyText
    label: NonEmptyText
    metro_line_id: NonEmptyText
    interchange: Interchange


def index_connections(
    layouts: Mapping[str, StationLayoutResponse],
) -> dict[str, ConnectionDataResponse]:
    """Build the lookup table from connection ID to its station data.

    Args:
        layouts: validated station layouts, keyed by interchange ID.

    Returns:
        One response per connection, keyed by connection ID.

    Raises:
        ValueError: two interchanges use the same connection ID. Layout
            validation only checks IDs within one interchange, and a repeated ID
            here would make a request return the wrong station.
    """
    connections: dict[str, ConnectionDataResponse] = {}
    for layout in layouts.values():
        for connection in layout.connections:
            if connection.id in connections:
                raise ValueError(f"duplicate connection ID: {connection.id!r}")
            connections[connection.id] = ConnectionDataResponse(
                connection=connection, station_layout=layout
            )
    return connections


def list_connections(
    connections: Mapping[str, ConnectionDataResponse],
) -> list[ConnectionSummary]:
    """Summarize every indexed connection for the catalog-listing endpoint.

    Reuses `index_connections`'s lookup table rather than the raw catalog, so
    the list can never name a connection `/connections/{id}` would reject.
    The metro line comes from the connection's metro-side platform
    (`to_platform_id`), the same platform the front end's selector already
    reads to show each connection's line.

    Args:
        connections: the lookup table built by `index_connections`.

    Returns:
        One summary per connection, in the same order as `connections`.
    """
    summaries = []
    for data in connections.values():
        platforms_by_id = {
            platform.platform_id: platform for platform in data.station_layout.platforms
        }
        metro_platform = platforms_by_id[data.connection.to_platform_id]
        summaries.append(
            ConnectionSummary(
                id=data.connection.id,
                label=data.connection.label,
                metro_line_id=metro_platform.line_id,
                interchange=data.station_layout.interchange,
            )
        )
    return summaries
