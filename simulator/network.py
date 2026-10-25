# AI contribution: 50% or more AI-generated
"""Construct static interchange topology from validated saved platforms.

Complex identities are the saved interchange IDs used as runtime station IDs.
Topology owns memberships; runtime components own queues and movement.
"""

import logging
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from simulator.network_config import NetworkConfig
from simulator.timetable import Platform

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StationComplex:
    """One combined REM–Métro location and its directional platforms."""

    interchange_id: str
    platform_ids: tuple[str, ...]
    line_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Line:
    """Platforms grouped by saved line identity across all complexes."""

    line_id: str
    platform_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Corridor:
    """One bidirectional connection shared by every REM–Métro endpoint pair.

    The corridor uses its complex's identity in a separate corridor namespace.
    Endpoint groups describe connectivity, without queue or walking parameters.
    """

    corridor_id: str
    interchange_id: str
    rem_platform_ids: tuple[str, ...]
    metro_platform_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Network:
    """Static topology with read-only indexes returned by build_network."""

    platforms: Mapping[str, Platform]
    station_complexes: Mapping[str, StationComplex]
    lines: Mapping[str, Line]
    corridors: Mapping[str, Corridor]

    def corridor_for(
        self, origin_platform_id: str, destination_platform_id: str
    ) -> Corridor | None:
        """Return the shared corridor for a directed REM–Métro transfer.

        Known endpoints without a link return None. Unknown IDs raise KeyError
        naming the endpoint. Lookups take O(1) time and leave topology unchanged.
        """
        for endpoint, platform_id in (
            ("origin", origin_platform_id),
            ("destination", destination_platform_id),
        ):
            if platform_id not in self.platforms:
                raise KeyError(
                    f"{endpoint} platform {platform_id!r}: unknown platform ID"
                )
        origin = self.platforms[origin_platform_id]
        destination = self.platforms[destination_platform_id]
        if (
            origin.interchange_id != destination.interchange_id
            or origin.line_id == destination.line_id
        ):
            return None
        # Construction guarantees one REM and one Métro line per complex.
        return self.corridors[origin.interchange_id]


def _index_platforms(config: NetworkConfig) -> dict[str, Platform]:
    if not config.platforms:
        raise ValueError("network platforms must not be empty")
    platforms = {}
    for platform in sorted(config.platforms, key=lambda p: p.platform_id):
        if platform.platform_id in platforms:
            raise ValueError(f"platform {platform.platform_id}: duplicate platform ID")
        platforms[platform.platform_id] = platform
    return platforms


def _build_complex(
    interchange_id: str, platforms: list[Platform]
) -> tuple[StationComplex, Corridor]:
    platform_ids_by_line = defaultdict(dict)
    for platform in platforms:
        platform_ids_by_direction = platform_ids_by_line[platform.line_id]
        if platform.direction_id in platform_ids_by_direction:
            raise ValueError(
                f"complex {interchange_id}, line {platform.line_id}, "
                f"platform {platform.platform_id}: duplicate direction "
                f"{platform.direction_id}"
            )
        platform_ids_by_direction[platform.direction_id] = platform.platform_id
    if len(platform_ids_by_line) != 2 or "rem" not in platform_ids_by_line:
        raise ValueError(
            f"complex {interchange_id}: expected one REM and one Métro line group"
        )
    for line_id, platform_ids_by_direction in platform_ids_by_line.items():
        if set(platform_ids_by_direction) != {0, 1}:
            raise ValueError(
                f"complex {interchange_id}, line {line_id}: expected directions 0 and 1"
            )
    metro_line = next(line_id for line_id in platform_ids_by_line if line_id != "rem")
    station = StationComplex(
        interchange_id=interchange_id,
        platform_ids=tuple(p.platform_id for p in platforms),
        line_ids=tuple(sorted(platform_ids_by_line)),
    )
    corridor = Corridor(
        corridor_id=interchange_id,
        interchange_id=interchange_id,
        rem_platform_ids=tuple(sorted(platform_ids_by_line["rem"].values())),
        metro_platform_ids=tuple(sorted(platform_ids_by_line[metro_line].values())),
    )
    return station, corridor


def build_network(config: NetworkConfig) -> Network:
    """Build the full supplied topology, rejecting incomplete corridor groups.

    The saved reader owns record validation and #88 owns geographic verification.
    This builder checks structural completeness without inspecting schedules.
    Construction takes O(P log P) time and O(P) space for P platforms.
    """
    platforms = _index_platforms(config)
    platforms_by_complex = defaultdict(list)
    platform_ids_by_line = defaultdict(list)
    for platform in platforms.values():
        platforms_by_complex[platform.interchange_id].append(platform)
        platform_ids_by_line[platform.line_id].append(platform.platform_id)
    station_complexes, corridors = {}, {}
    for interchange_id in sorted(platforms_by_complex):
        station, corridor = _build_complex(
            interchange_id, platforms_by_complex[interchange_id]
        )
        station_complexes[interchange_id] = station
        corridors[interchange_id] = corridor
    lines = {
        line_id: Line(
            line_id=line_id, platform_ids=tuple(platform_ids_by_line[line_id])
        )
        for line_id in sorted(platform_ids_by_line)
    }
    network = Network(
        platforms=MappingProxyType(platforms),
        station_complexes=MappingProxyType(station_complexes),
        lines=MappingProxyType(lines),
        corridors=MappingProxyType(corridors),
    )
    log.info(
        "Built network: %d station complexes, %d lines, %d platforms, %d corridors",
        len(station_complexes),
        len(lines),
        len(platforms),
        len(corridors),
    )
    return network
