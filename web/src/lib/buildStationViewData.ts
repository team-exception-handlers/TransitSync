// AI contribution: 50% or more AI-generated

import type {
    InterchangeMapping,
    LineId,
    MockInterchangeData,
    Platform,
    StationViewData,
} from "../types/stationView";

import { parseStationViewData } from "./validateStationView";

const LINE_COLORS: Record<LineId, string> = {
    rem: "#84b819",
    orange: "#f08123",
    green: "#00923f",
    blue: "#0072bc",
};

export function buildStationViewData(
    mapping: InterchangeMapping,
    mock: MockInterchangeData,
): StationViewData {
    if (
        mock.schema_version !== 1 ||
        !mock.interchange ||
        typeof mock.interchange.id !== "string" ||
        !mock.platform_layouts
    ) {
        throw new Error("Invalid mock interchange");
    }

    const stationById = new Map(
        mock.stations.map((station) => [
            station.id,
            station,
        ]),
    );

    const platforms: Platform[] = [];
    const platformIds = new Set<string>();

    for (const [feedId, entries] of Object.entries(mapping)) {
        if (!Array.isArray(entries)) {
            throw new Error(`Invalid feed: ${feedId}`);
        }

        for (const entry of entries) {
            if (entry.interchange_id !== mock.interchange.id) {
                continue;
            }

            if (platformIds.has(entry.platform_id)) {
                throw new Error(
                    `Duplicate platform ID: ${entry.platform_id}`,
                );
            }

            const layout =
                mock.platform_layouts[entry.platform_id];

            if (!layout) {
                throw new Error(
                    `Missing platform layout: ${entry.platform_id}`,
                );
            }

            const station = stationById.get(layout.station_id);

            if (!station) {
                throw new Error(
                    `Unknown station for platform ${entry.platform_id}`,
                );
            }

            if (station.line_id !== entry.line_id) {
                throw new Error(
                    `Platform line mismatch: ${entry.platform_id}`,
                );
            }

            const color = LINE_COLORS[entry.line_id];

            if (!color) {
                throw new Error(
                    `Unknown line: ${entry.line_id}`,
                );
            }

            platforms.push({
                ...entry,

                source_feed_id: feedId,
                station_id: layout.station_id,

                position: layout.position,
                color,
            });

            platformIds.add(entry.platform_id);
        }
    }

    if (platforms.length === 0) {
        throw new Error(
            `No platforms for interchange ${mock.interchange.id}`,
        );
    }

    for (const id of Object.keys(mock.platform_layouts)) {
        if (!platformIds.has(id)) {
            throw new Error(`Unknown platform layout: ${id}`);
        }
    }

    const data: StationViewData = {
        schema_version: mock.schema_version,

        interchange: mock.interchange,

        start_clock_s: mock.start_clock_s,
        duration_s: mock.duration_s,

        map: mock.map,
        stations: mock.stations,

        platforms,

        corridors: mock.corridors,
        connections: mock.connections,

        passenger_tracks: mock.passenger_tracks,
        train_events: mock.train_events,

        passengers: [],
    };

    return parseStationViewData(data);
}