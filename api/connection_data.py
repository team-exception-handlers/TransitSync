# AI contribution: 50% or more AI-generated
"""Look up the station data that belongs to one selectable connection (#78).

The front end selects connections such as ``mcgill-rem-green``, while the layout
catalog is keyed by interchange. This module joins the two with a lookup table
built once at startup, so requests never search or parse the catalog.
"""

from collections.abc import Mapping

from api.station_layout import Connection, StationLayoutResponse, StrictModel


class ConnectionDataResponse(StrictModel):
    """One connection and the map data for the interchange that contains it.

    The whole layout is returned rather than only the connection's two
    platforms: train events use every directional platform at the interchange,
    so a run could not be drawn from the connection's endpoints alone.
    """

    connection: Connection
    station_layout: StationLayoutResponse


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
