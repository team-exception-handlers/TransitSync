// AI contribution: 50% or more AI-generated
/**
 * Join the backend platform mapping with a mock run's map layout to produce the
 * validated data the station view draws. Every mapped platform for the run's
 * interchange must have a layout, and every layout must belong to a mapped
 * platform, so the map never shows a platform the backend does not know.
 */

import type {
    InterchangeMapping,
    LineId,
    MockInterchangeData,
    Platform,
    PlatformMappingEntry,
    Station,
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
    checkMockHeader(mock);
    const platforms = collectPlatforms(mapping, mock);
    checkEveryLayoutIsMapped(mock, platforms);

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

/** Reject a mock run without the schema version, interchange ID or layouts this code reads. */
function checkMockHeader(mock: MockInterchangeData): void {
    if (
        mock.schema_version !== 1 ||
        !mock.interchange ||
        typeof mock.interchange.id !== "string" ||
        !mock.platform_layouts
    ) {
        throw new Error("Invalid mock interchange");
    }
}

/**
 * Build one platform per mapping entry for the run's interchange, in mapping
 * order. Entries for other interchanges are skipped; a platform ID may appear
 * only once across all feeds.
 */
function collectPlatforms(
    mapping: InterchangeMapping,
    mock: MockInterchangeData,
): Platform[] {
    const stationById = new Map(mock.stations.map((station) => [station.id, station]));
    const platforms: Platform[] = [];
    const platformIds = new Set<string>();

    for (const [feedId, entries] of Object.entries(mapping)) {
        if (!Array.isArray(entries)) {
            throw new Error(`Invalid feed: ${feedId}`);
        }
        for (const entry of entries) {
            if (entry.interchange_id !== mock.interchange.id) continue;
            if (platformIds.has(entry.platform_id)) {
                throw new Error(`Duplicate platform ID: ${entry.platform_id}`);
            }
            platforms.push(toPlatform(feedId, entry, mock, stationById));
            platformIds.add(entry.platform_id);
        }
    }

    if (platforms.length === 0) {
        throw new Error(`No platforms for interchange ${mock.interchange.id}`);
    }
    return platforms;
}

/**
 * Attach a mapping entry's map position, station and line color. The layout
 * must exist, point to a known station on the same line, and the line must
 * have a map color.
 */
function toPlatform(
    feedId: string,
    entry: PlatformMappingEntry,
    mock: MockInterchangeData,
    stationById: ReadonlyMap<string, Station>,
): Platform {
    const layout = mock.platform_layouts[entry.platform_id];
    if (!layout) {
        throw new Error(`Missing platform layout: ${entry.platform_id}`);
    }
    const station = stationById.get(layout.station_id);
    if (!station) {
        throw new Error(`Unknown station for platform ${entry.platform_id}`);
    }
    if (station.line_id !== entry.line_id) {
        throw new Error(`Platform line mismatch: ${entry.platform_id}`);
    }
    const color = LINE_COLORS[entry.line_id];
    if (!color) {
        throw new Error(`Unknown line: ${entry.line_id}`);
    }
    return {
        ...entry,
        source_feed_id: feedId,
        station_id: layout.station_id,
        position: layout.position,
        color,
    };
}

/** Reject a layout that no mapped platform uses, so the map shows only real platforms. */
function checkEveryLayoutIsMapped(mock: MockInterchangeData, platforms: Platform[]): void {
    const platformIds = new Set(platforms.map((platform) => platform.platform_id));
    for (const id of Object.keys(mock.platform_layouts)) {
        if (!platformIds.has(id)) {
            throw new Error(`Unknown platform layout: ${id}`);
        }
    }
}
