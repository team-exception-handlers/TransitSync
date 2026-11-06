"""Load and validate the static station layout catalog served by the API."""

import json
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

CONFIG_ROOT = Path(__file__).resolve().parents[1] / "config"
LAYOUT_PATH = CONFIG_ROOT / "station_layouts.json"
NETWORK_PATH = CONFIG_ROOT / "reference_network" / "network.json"
NonEmptyText = Annotated[str, Field(min_length=1)]
LINE_COLORS = {
    "rem": "#84b819",
    "orange": "#f08123",
    "green": "#00923f",
    "blue": "#0072bc",
}


class StrictModel(BaseModel):
    """Reject unknown fields so committed layout schema drift fails at startup."""

    model_config = ConfigDict(extra="forbid")


class Point(StrictModel):
    """A finite, non-negative point measured in map pixels.

    The origin is at the map's upper-left corner.
    """

    x: float = Field(ge=0, allow_inf_nan=False)
    y: float = Field(ge=0, allow_inf_nan=False)


class Interchange(StrictModel):
    """A layout identity and user-facing display label.

    The ID matches the catalog key; the name is map-selector text.
    """

    id: NonEmptyText
    name: NonEmptyText


class MapSize(StrictModel):
    """Positive map dimensions in pixels."""

    width: int = Field(gt=0, strict=True)
    height: int = Field(gt=0, strict=True)


class Station(StrictModel):
    """A station marker positioned in the map's pixel coordinate space.

    The line ID is derived from its platforms, not repeated in geometry.
    """

    id: NonEmptyText
    name: NonEmptyText
    line_id: NonEmptyText
    position: Point


class StationGeometry(StrictModel):
    """Map-only station marker data; line identity comes from its platforms.

    The separate line-free shape keeps layout JSON free of duplicated metadata.
    """

    id: NonEmptyText
    name: NonEmptyText
    position: Point


class Platform(StrictModel):
    """Directional platform metadata enriched with map drawing data.

    Position uses pixels; source_feed_id identifies the mapping's feed.
    """

    platform_id: NonEmptyText
    interchange_id: NonEmptyText
    line_id: NonEmptyText
    direction_id: int = Field(ge=0, le=1, strict=True)
    direction_label: NonEmptyText
    stop_id: NonEmptyText
    stop_name: NonEmptyText
    route_ids: list[NonEmptyText] = Field(min_length=1)
    station_id: NonEmptyText
    source_feed_id: NonEmptyText
    position: Point
    color: NonEmptyText


class PlatformMetadata(StrictModel):
    """Platform details sourced from the validated reference-network data.

    The feed ID is the original source for the response's source_feed_id field.
    """

    feed_id: NonEmptyText
    platform_id: NonEmptyText
    interchange_id: NonEmptyText
    line_id: NonEmptyText
    direction_id: int = Field(ge=0, le=1, strict=True)
    direction_label: NonEmptyText
    stop_id: NonEmptyText
    stop_name: NonEmptyText
    route_ids: list[NonEmptyText] = Field(min_length=1)


class PlatformLayout(StrictModel):
    """Map-only station association and pixel position for one platform.

    The platform ID is the mapping key, not another metadata record.
    """

    station_id: NonEmptyText
    position: Point


class Corridor(StrictModel):
    """A transfer edge with ordered pixel path points and platform endpoints.

    The path is drawn from from_platform_id to to_platform_id.
    """

    id: NonEmptyText
    label: NonEmptyText
    from_platform_id: NonEmptyText
    to_platform_id: NonEmptyText
    path: list[Point] = Field(min_length=2)


class Connection(StrictModel):
    """A selectable transfer joining two platforms through one corridor.

    Endpoint IDs and corridor_id must resolve within the same response.
    """

    id: NonEmptyText
    label: NonEmptyText
    from_platform_id: NonEmptyText
    to_platform_id: NonEmptyText
    corridor_id: NonEmptyText


class StationLayoutResponse(StrictModel):
    """Complete static map data for one interchange.

    Passenger tracks and train events are intentionally provided elsewhere.
    """

    interchange: Interchange
    map: MapSize
    stations: list[Station] = Field(min_length=1)
    platforms: list[Platform] = Field(min_length=1)
    corridors: list[Corridor] = Field(min_length=1)
    connections: list[Connection] = Field(min_length=1)


class LayoutGeometry(StrictModel):
    """Station and transfer geometry for one interchange.

    Network platform descriptions are joined at API startup, not stored here.
    """

    interchange: Interchange
    map: MapSize
    stations: list[StationGeometry] = Field(min_length=1)
    platform_layouts: dict[NonEmptyText, PlatformLayout]
    corridors: list[Corridor] = Field(min_length=1)
    connections: list[Connection] = Field(min_length=1)


class LayoutCatalog(StrictModel):
    """Committed map geometry, separate from reference-network metadata."""

    layouts: dict[NonEmptyText, LayoutGeometry]


PLATFORM_METADATA_ADAPTER = TypeAdapter(list[PlatformMetadata])


def _read_reference_network() -> list[PlatformMetadata]:
    """Load platform source records from the existing reference network.

    File, JSON, and Pydantic errors propagate so API startup cannot silently
    switch to duplicated or partial station metadata.
    """
    content = json.loads(NETWORK_PATH.read_text(encoding="utf-8"))
    if not isinstance(content, dict) or not isinstance(content.get("schedules"), list):
        raise ValueError("reference network must contain schedules")
    schedules = content["schedules"]
    if not schedules or any(
        not isinstance(schedule, dict)
        or not isinstance(schedule.get("platforms"), list)
        for schedule in schedules
    ):
        raise ValueError("reference network schedule must contain platforms")
    platform_rows = [p for schedule in schedules for p in schedule["platforms"]]
    return PLATFORM_METADATA_ADAPTER.validate_python(platform_rows)


def _index_platform_metadata(
    platforms: list[PlatformMetadata],
) -> dict[str, PlatformMetadata]:
    """Deduplicate stable platform metadata repeated across saved schedules.

    Conflicting records fail validation instead of making output depend on
    schedule ordering.
    """
    platforms_by_id: dict[str, PlatformMetadata] = {}
    for platform in platforms:
        existing = platforms_by_id.get(platform.platform_id)
        if existing is not None and existing != platform:
            raise ValueError(f"conflicting reference platform {platform.platform_id!r}")
        platforms_by_id[platform.platform_id] = platform
    return platforms_by_id


def _build_platforms(
    interchange_id: str,
    geometry: LayoutGeometry,
    metadata_by_id: dict[str, PlatformMetadata],
) -> list[Platform]:
    """Join canonical network metadata with this interchange's map positions."""
    mapped_ids = {
        platform_id
        for platform_id, platform in metadata_by_id.items()
        if platform.interchange_id == interchange_id
    }
    if mapped_ids != set(geometry.platform_layouts):
        raise ValueError(
            f"{interchange_id}: platform geometry does not match reference network"
        )

    platforms = []
    for platform_id, platform_layout in geometry.platform_layouts.items():
        metadata = metadata_by_id[platform_id]
        color = LINE_COLORS.get(metadata.line_id)
        if color is None:
            raise ValueError(
                f"platform {platform_id!r}: no map color for line {metadata.line_id!r}"
            )
        platforms.append(
            Platform(
                **metadata.model_dump(exclude={"feed_id"}),
                station_id=platform_layout.station_id,
                source_feed_id=metadata.feed_id,
                position=platform_layout.position,
                color=color,
            )
        )
    return platforms


def _build_stations(
    geometry: LayoutGeometry, platforms: list[Platform]
) -> list[Station]:
    """Derive each station line from its mapped canonical platform records.

    A station with no platforms or platforms from multiple lines is invalid.
    """
    station_lines: dict[str, str] = {}
    for platform in platforms:
        line_id = station_lines.setdefault(platform.station_id, platform.line_id)
        if line_id != platform.line_id:
            raise ValueError(
                f"station {platform.station_id!r}: platforms use multiple lines"
            )
    if any(station.id not in station_lines for station in geometry.stations):
        raise ValueError("station geometry has no mapped platforms")
    return [
        Station(
            id=station.id,
            name=station.name,
            line_id=station_lines[station.id],
            position=station.position,
        )
        for station in geometry.stations
    ]


def _validate_references(layout: StationLayoutResponse) -> None:
    """Reject duplicate or dangling station, platform, and corridor references.

    Map points must fit inside the pixel dimensions; invalid references raise
    ValueError during application startup.
    """
    station_by_id = {station.id: station for station in layout.stations}
    platforms_by_id = {platform.platform_id: platform for platform in layout.platforms}
    corridor_ids = {corridor.id for corridor in layout.corridors}
    identifiers = (
        ("station", station_by_id, len(layout.stations)),
        ("platform", platforms_by_id, len(layout.platforms)),
        ("corridor", corridor_ids, len(layout.corridors)),
        (
            "connection",
            {item.id for item in layout.connections},
            len(layout.connections),
        ),
    )
    for label, unique_ids, count in identifiers:
        if len(unique_ids) != count:
            raise ValueError(f"{layout.interchange.id}: duplicate {label} ID")

    positions = [
        *(station.position for station in layout.stations),
        *(platform.position for platform in layout.platforms),
        *(point for corridor in layout.corridors for point in corridor.path),
    ]
    if any(
        point.x > layout.map.width or point.y > layout.map.height for point in positions
    ):
        raise ValueError(f"{layout.interchange.id}: map point is outside map bounds")

    if any(
        platform.interchange_id != layout.interchange.id
        or platform.station_id not in station_by_id
        or platform.line_id != station_by_id[platform.station_id].line_id
        for platform in layout.platforms
    ):
        raise ValueError(
            f"{layout.interchange.id}: platform has an invalid station or "
            "interchange reference"
        )
    if any(
        corridor.from_platform_id not in platforms_by_id
        or corridor.to_platform_id not in platforms_by_id
        for corridor in layout.corridors
    ) or any(
        connection.from_platform_id not in platforms_by_id
        or connection.to_platform_id not in platforms_by_id
        or connection.corridor_id not in corridor_ids
        for connection in layout.connections
    ):
        raise ValueError(
            f"{layout.interchange.id}: transfer has an unknown platform or corridor"
        )


def load_station_layouts() -> dict[str, StationLayoutResponse]:
    """Load map geometry and join canonical platform metadata for each interchange.

    A mismatched catalog key or invalid reference raises ValueError during app
    creation; the endpoint never substitutes a fallback layout. Platform
    descriptions come from network.json, while this API's catalog stores only
    the station and transfer coordinates not present there. Returns layouts
    keyed by interchange ID.
    """
    catalog = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
    geometries = LayoutCatalog.model_validate(catalog).layouts
    metadata_by_id = _index_platform_metadata(_read_reference_network())
    layouts = {}
    for interchange_id, geometry in geometries.items():
        if interchange_id != geometry.interchange.id:
            raise ValueError(f"catalog key does not match layout ID: {interchange_id}")
        platforms = _build_platforms(interchange_id, geometry, metadata_by_id)
        layout = StationLayoutResponse(
            interchange=geometry.interchange,
            map=geometry.map,
            stations=_build_stations(geometry, platforms),
            platforms=platforms,
            corridors=geometry.corridors,
            connections=geometry.connections,
        )
        _validate_references(layout)
        layouts[interchange_id] = layout
    return layouts
