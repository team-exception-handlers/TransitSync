// AI contribution: 50% or more AI-generated
/**
 * Validate station-view data before the map uses it, then derive passenger
 * movements. Checks run in a fixed order (header, stations, platforms,
 * corridors, connections, passenger tracks, train events), and each step only
 * accepts references to IDs the earlier steps already validated, so the first
 * problem found is the one reported.
 */

import type {
    Connection,
    PassengerPhase,
    PassengerTrack,
    Platform,
    Point,
    Station,
    StationViewData,
    TrainMovementEvent,
    TransferCorridor,
} from "../types/stationView";

import { derivePassengerMovements } from "./passengerMovements";

const VALID_PHASES = new Set<PassengerPhase>([
    "walking",
    "queued",
    "waiting",
    "boarding",
    "boarded",
    "missed",
]);

const TRAIN_EVENT_TYPES = ["train_arrival", "train_departure"];

function isPoint(value: unknown): value is Point {
    if (typeof value !== "object" || value === null) {
        return false;
    }

    const point = value as Record<string, unknown>;

    return (
        typeof point.x === "number" &&
        Number.isFinite(point.x) &&
        typeof point.y === "number" &&
        Number.isFinite(point.y)
    );
}

function isNonNegativeNumber(value: unknown): value is number {
    return (
        typeof value === "number" &&
        Number.isFinite(value) &&
        value >= 0
    );
}

export function parseStationViewData(
    value: unknown,
): StationViewData {
    const data = checkHeader(value);

    // Each collection is checked against the IDs collected just before it.
    const stationIds = collectUniqueIds(
        data.stations, "station", (station) => station.id,
        isValidStation, () => "Invalid station",
    );
    const platformIds = collectUniqueIds(
        data.platforms, "platform", (platform) => platform.platform_id,
        (platform) => isValidPlatform(platform, stationIds), () => "Invalid platform",
    );
    const corridorIds = collectUniqueIds(
        data.corridors, "corridor", (corridor) => corridor.id,
        (corridor) => isValidCorridor(corridor, platformIds),
        (corridor) => `Invalid corridor: ${corridor.id}`,
    );
    const connectionIds = collectUniqueIds(
        data.connections, "connection", (connection) => connection.id,
        (connection) => isValidConnection(connection, platformIds, corridorIds),
        (connection) => `Invalid connection: ${connection.id}`,
    );
    checkPassengerTracks(data.passenger_tracks, connectionIds, data.duration_s);
    checkTrainEvents(data.train_events, data.platforms, data.duration_s);

    // Return the validated data with passengers automatically derived
    return {
        ...data,
        passengers: derivePassengerMovements(data.passenger_tracks),
    };
}

/** Check the object itself, its schema version, metadata, map size and that every collection is a list. */
function checkHeader(value: unknown): StationViewData {
    if (typeof value !== "object" || value === null) {
        throw new Error("Station view data must be an object");
    }

    const data = value as StationViewData;

    if (data.schema_version !== 1) {
        throw new Error("Unsupported station view schema version");
    }

    if (
        !data.interchange ||
        typeof data.interchange.id !== "string" ||
        typeof data.interchange.name !== "string"
    ) {
        throw new Error("Invalid interchange");
    }

    if (
        !isNonNegativeNumber(data.start_clock_s) ||
        !isNonNegativeNumber(data.duration_s)
    ) {
        throw new Error("Invalid simulation time metadata");
    }

    if (!hasPositiveSize(data.map)) {
        throw new Error("Invalid map dimensions");
    }

    const collections = [
        data.stations, data.platforms, data.corridors,
        data.connections, data.passenger_tracks, data.train_events,
    ];
    if (!collections.every((collection) => Array.isArray(collection))) {
        throw new Error("Invalid station view collections");
    }
    return data;
}

/** The map box must exist and have a finite, non-zero width and height. */
function hasPositiveSize(map: StationViewData["map"] | undefined): boolean {
    return (
        !!map &&
        isNonNegativeNumber(map.width) &&
        isNonNegativeNumber(map.height) &&
        map.width > 0 &&
        map.height > 0
    );
}

/**
 * Validate each item, reject repeated IDs, and return the IDs for later steps
 * to check references against. `kind` names the item in the duplicate
 * message; `invalidMessage` builds the message for a bad item.
 */
function collectUniqueIds<T>(
    items: readonly T[],
    kind: string,
    idOf: (item: T) => string,
    isValid: (item: T) => boolean,
    invalidMessage: (item: T) => string,
): Set<string> {
    const ids = new Set<string>();
    for (const item of items) {
        if (!isValid(item)) {
            throw new Error(invalidMessage(item));
        }
        const id = idOf(item);
        if (ids.has(id)) {
            throw new Error(`Duplicate ${kind}: ${id}`);
        }
        ids.add(id);
    }
    return ids;
}

function isValidStation(station: Station): boolean {
    return (
        typeof station.id === "string" &&
        typeof station.name === "string" &&
        isPoint(station.position)
    );
}

/** A platform needs its backend IDs, a whole-number direction, string routes and a known station. */
function isValidPlatform(platform: Platform, stationIds: Set<string>): boolean {
    return (
        typeof platform.platform_id === "string" &&
        typeof platform.stop_id === "string" &&
        typeof platform.direction_label === "string" &&
        Number.isInteger(platform.direction_id) &&
        Array.isArray(platform.route_ids) &&
        platform.route_ids.every((route) => typeof route === "string") &&
        isPoint(platform.position) &&
        stationIds.has(platform.station_id)
    );
}

/** A corridor joins two known platforms along a path of at least two points. */
function isValidCorridor(corridor: TransferCorridor, platformIds: Set<string>): boolean {
    return (
        typeof corridor.id === "string" &&
        platformIds.has(corridor.from_platform_id) &&
        platformIds.has(corridor.to_platform_id) &&
        Array.isArray(corridor.path) &&
        corridor.path.length >= 2 &&
        corridor.path.every(isPoint)
    );
}

function isValidConnection(
    connection: Connection,
    platformIds: Set<string>,
    corridorIds: Set<string>,
): boolean {
    return (
        typeof connection.id === "string" &&
        platformIds.has(connection.from_platform_id) &&
        platformIds.has(connection.to_platform_id) &&
        corridorIds.has(connection.corridor_id)
    );
}

/**
 * Each track belongs to a known connection and a unique passenger. Its samples
 * are checked after the track itself, so a duplicate passenger is reported
 * before a bad sample.
 */
function checkPassengerTracks(
    tracks: readonly PassengerTrack[],
    connectionIds: Set<string>,
    duration_s: number,
): void {
    const passengerIds = new Set<string>();
    for (const track of tracks) {
        if (
            typeof track.passenger_id !== "string" ||
            typeof track.group_id !== "string" ||
            !connectionIds.has(track.connection_id) ||
            !Array.isArray(track.samples)
        ) {
            throw new Error("Invalid passenger track");
        }
        if (passengerIds.has(track.passenger_id)) {
            throw new Error(`Duplicate passenger: ${track.passenger_id}`);
        }
        passengerIds.add(track.passenger_id);
        checkSamples(track.samples, duration_s);
    }
}

/** Samples must be strictly increasing in time, inside the run, with a position and a known phase. */
function checkSamples(samples: PassengerTrack["samples"], duration_s: number): void {
    let previousTime = -Infinity;
    for (const sample of samples) {
        if (
            !isNonNegativeNumber(sample.time_s) ||
            sample.time_s <= previousTime ||
            sample.time_s > duration_s ||
            !isPoint(sample.position) ||
            !VALID_PHASES.has(sample.phase)
        ) {
            throw new Error("Invalid passenger samples");
        }
        previousTime = sample.time_s;
    }
}

/** Every train event happens at a known platform within the run. */
function checkTrainEvents(
    events: readonly TrainMovementEvent[],
    platforms: readonly Platform[],
    duration_s: number,
): void {
    const platformsById = new Map(platforms.map((platform) => [platform.platform_id, platform]));
    for (const event of events) {
        const platform = platformsById.get(event.platform_id);
        if (
            !TRAIN_EVENT_TYPES.includes(event.event_type) ||
            typeof event.train_id !== "string" ||
            !platform ||
            !isNonNegativeNumber(event.time_s) ||
            !isNonNegativeNumber(event.scheduled_s) ||
            event.time_s > duration_s
        ) {
            throw new Error("Invalid train event");
        }
        // Explicit convention for this mock:
        // train-event station_id equals backend stop_id.
        if (event.station_id !== platform.stop_id) {
            throw new Error(`Station/stop mismatch for ${event.train_id}`);
        }
    }
}
